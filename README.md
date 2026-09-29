# cad-agent

Agent-driven mechanical CAD. Parametric parts in Python, deterministic gates,
headless renders, and an independent verifier. A harness: agents drive it from
the shell, and a design is done only when `cad verify` says so.

```
bin/cad --help                                   # every command, and the exit codes
bin/cad --projects <dir> check <slug>            # run every gate
bin/cad --projects <dir> verify <slug>           # rebuild fresh, record the verdict with git
bin/cad --projects <dir> done <slug>             # the gate: exit 0 only if that verdict still stands
.venv/bin/python -m pytest tests -q              # 181 tests
```

Open a Claude Code session in this repo and it loads the harness from `.claude/`:
- the `/cad` skill, with the design loop
- a hook that runs `cad check` after every edit to a design file and feeds back what fails
- a stop hook that won't let a changed project go unverified without saying so
- the read-only `cad-reviewer` agent
- permission to run `bin/cad`

Each project states what it must do in `spec.toml` (envelope, clearances, tool
keep-outs, mass budgets, bolt holes that must line up), and the `spec` gate
checks every entry. A project without one is UNCHECKED. See
`cad_agent/spec.py` for the format and `tests/fixtures/*/spec.toml` for real
examples.

Projects live wherever you keep them: `--projects DIR` or `CAD_PROJECTS`, or
`projects/` here by default. The first call starts a warm worker that imports
the CAD kernel once (20–35 s), then each command takes about a second;
`CAD_WARM=0` runs cold. The v2 plan, the research map behind it, and what is
built are in PLAN_V2.md. The MCP server it replaced was retired on 2026-09-28;
`python -m cad_agent` now runs the same CLI, cold.

## Why build123d and not a GUI CAD

The loop is: change a parameter, rebuild, measure interference, render, look,
repeat, in seconds, with no application running and every change visible in a
git diff. That needs a code-first B-rep kernel.

- **OpenSCAD** has no edges and no B-rep, so there is no fillet on a selected
  face, no STEP import of a vendor part, and no way to ask how close two
  solids are. Fit checking becomes squinting at a picture.
- **FreeCAD** is scriptable and headless, but the document is a binary
  `.FCStd` with no diff, and topological naming breaks a model when an
  earlier feature changes — the worst possible property for a loop that edits
  parameters every iteration. Its kernel is OCCT, which is what build123d
  gives us without the document layer.
- **Fusion 360 / SolidWorks** script only inside a running, licensed GUI. No
  headless, no CI.
- **Onshape** has a real API but every rebuild is a network round trip and the
  design lives on someone else's server.

Exporting STEP and opening it in FreeCAD to look or dimension is fine. The
Python stays the source of truth.

## Layout

```
cad_agent/
  geom.py       OCCT queries: min distance, overlap volume, mass, bbox
  parts.py      ISO 273 hole tables, tap drills, insert bores, extrusions
  render.py     tessellate, backend dispatch, numpy z-buffer fallback, PNG writer
  metal_render.py  GPU rasteriser via PyObjC Metal. Offscreen, no window
  checks/fit.py every pair: interference volume or measured gap vs required
  checks/dfm.py per process: envelope, measured wall, in-plane web, feature count
  checks/web.py section a flat part, measure the material between its boundaries
  thickness.py  ray-cast wall thickness, so a part cannot declare its own
  runner.py     check_all writes checks.json; done_check is the gate
  bought.py     vendor STEP or measured-with-a-source geometry, provenance enforced
  registry.py   the check registry: Row, scopes, and the @register decorator
  rules.py      every check, registered. The list of what a run verifies
  checks/visual.py  render drift against approved baselines, with diff images
  cutlist.py    stock derived from each part's CUTLIST, roughly priced
  export.py     STEP for a shop, STL for a printer
  cli.py        the cad CLI: every command, --json, exit codes, activity log
  warm.py       the warm worker: kernel imported once, a fresh fork per command
  verify.py     the verifier: fresh rebuild, source and engine hashes, git, cad done
  spec.py       spec.toml, the brief as acceptance tests
.claude/        the /cad skill, the check and stop hooks, the cad-reviewer agent
projects/<slug>/
  mech_profile.md  parts/*.py  assembly.py  bought/*.step  out/  checks.json
```

## Render backend

Two backends, chosen automatically. `cad --version` and `cad tables` both
name the one in use.

**Metal, the default.** macOS has no EGL, so the usual headless OpenGL path
does not exist and pyrender cannot start. Metal is Apple's supported route and
PyObjC reaches it, so `metal_render.py` talks to it directly: an offscreen
colour texture plus a depth texture, one render pass, no window and no
window-server session. It works over ssh and in a subprocess. Shading is
computed in numpy and the triangles are sent unindexed, so each carries its
own flat colour and the shader needs no per-primitive data.

**numpy z-buffer, the fallback.** Pure numpy, hand-rolled PNG writer, no
image library and no GPU. Kept so a machine without Metal renders rather than
fails. `CAD_RENDER_BACKEND=numpy` forces it.

A test asserts the two agree pixel for pixel within edge-coverage noise, so a
render is evidence either way.

| Subject | Triangles | numpy | Metal | |
|---|---|---|---|---|
| hot plate | 2,620 | 0.98 s | 0.021 s | 47x |
| assembly, 7 parts | 5,668 | 0.73 s | 0.027 s | 27x |
| fine torus | 127,008 | 10.4 s | 0.396 s | 26x |
| very fine sphere | 201,558 | 16.1 s | 0.610 s | 26x |

The numpy path loops over triangles in Python, so it grows with triangle
count in a way the GPU does not. Metal keeps a dense model interactive.

## Bought parts carry provenance

Geometry for a bought part comes from the vendor, never from memory. A
remembered bolt circle is how an assembly passes every check and still does
not fit. Two routes, both recording where the numbers came from:

- **STEP** — the vendor's file in `projects/<slug>/bought/`, with a sidecar
  naming the page it came from. Registering one without a source is refused.
- **MEASURED** — a module declaring dimensions with a `SOURCE` naming the
  drawing, datasheet page or calliper reading. No `SOURCE`, no load.

Either may set `VERIFIED = False` for numbers taken from a listing that never
published them. That is reported everywhere the part appears and fails
`done_check`, so an unconfirmed dimension cannot quietly become load-bearing.

A STEP carries its donor assembly's coordinates, so an assembly must
re-origin bought geometry rather than assume it is centred. The SK-Cube
bracket in the first project lands at (-270.8, -541.0, 171.5).

## Adding a check is one function

Checks live in `rules.py` and register themselves. The runner discovers them,
the gate consumes them, and the report prints them, with no other edit:

```python
@register(scope="part", name="web")
def web_rule(ctx):
    yield Row(subject=ctx.name, rule="web", state="PASS",
              measured="4.1 mm at (-82.9, -9.2)", limit="1.5 mm",
              source="closest approach over 120 boundary pairs")
```

Scope decides what the runner hands you: `part` once per part with the built
solid, `assembly` once with every positioned solid and the clearance table,
`project` once with the whole directory. `cad rules` prints what is
registered.

Four states, and only four. `UNCHECKED` is not a pass — it means a rule could
not be settled, and it fails the gate exactly as a failure does. `N/A` is
different: the rule does not apply to this subject. Every row names its limit
and where that limit came from, so a reader can disagree with the threshold
rather than with the number. A check that raises becomes one `UNCHECKED` row
instead of killing the run, because one broken rule must not hide the rest.

Shipped checks:

| Check | Scope | Verifies |
|---|---|---|
| `geometry` | part | envelope, measured wall, in-plane web, feature count |
| `visual` | part | silhouette coverage, drift from the approved render, drawn extent |
| `fit` | assembly | interference and clearance, every pair |
| `stance` | assembly | footprint area at the contact plane |
| `provenance` | project | whether each bought part records, and confirms, its source |

## Visual regression

A render is a checkable artifact. Approve an image once, and every later run
reports what fraction of the frame changed and writes a diff with the changed
pixels marked in red. Change a parameter and the run tells you which views
moved and by how much, instead of you flicking between pictures.

Until a view is approved its drift rule is `UNCHECKED`, so a project with no
baselines does not silently pass. Approve with `approve_render`, but look at
the diff first: approving blindly is how the rule gets turned off.

Three rules come out of the same pair of images. **Silhouette** is the
fraction of the frame the part covers, and near zero is how a broken build
looks when the solid is empty but the render still succeeds. **Drift** is the
fraction of pixels that differ. **Extent** is whether the drawn bounding box
moved, which separates a change of shape from a change of position or scale.

Tolerances are stated in every row: a pixel counts as changed past a channel
difference of 24, and drift is a failure past 0.2% of the frame. Both exist
because rasterisation is not exact at silhouette edges.

## Nothing is taken on the part's word

Two rules used to be declared by the part and believed by the gate. Both are
measured now, after two faults reached a published page because nothing could
see them.

**Wall thickness** is ray cast through the solid: sample the surface, step
inside, shoot along the inward normal, and take the distance to the first
exit. It gates on the 1st percentile, because a grazing ray at a sharp edge
returns a near-zero distance that describes the tessellation rather than the
part. A part that understates its own thickness is corrected, not believed.

**Web width** works in the plane, because ray casting cannot see the fault it
catches: on a 3 mm sheet every inward ray measures 3 mm, whether it starts in
the middle of the plate or in the 0.8 mm strip between two slots. So flat
parts are sectioned instead, and the distance measured between the outer
boundary and every cutout. One section yields three rules:

| Rule | Catches |
|---|---|
| web width | a hole too near an edge, or two cutouts nearly meeting |
| feature count | one cutout swallowing another, or breaking out through an edge |
| region count | a part severed into pieces by its own features |

The web rule reports the coordinate of the narrow point. A failure naming an
anonymous feature index cannot be acted on.

## The gates fail, they do not report

`done_check` returns `ok:false` on any FAIL **and** on any UNCHECKED. A wall
thickness that was never measured is not a pass. This is deliberate: an
unreviewed finding that joins a pile is a finding nobody acts on.

`N/A` is distinct from a pass: it marks a rule that does not apply, such as
the in-plane web rule on a chunky part.

## First project

`projects/desk_fab_line` — the two-cell Desk Fab Line. Built so far: the
reflow hot plate and its ceramic standoffs, docked over 2040 floor rails,
with the plate-to-frame air gap gated at 20 mm. The plate takes either a flat
mica element underneath or two cartridge bores, chosen by a parameter, because
which heater to buy is still open.

`done_check` is deliberately red on this project: the mica heater's dimensions
came from no published drawing, and the gate holds the project open until they
are confirmed. Geometry and manufacturability are green.
