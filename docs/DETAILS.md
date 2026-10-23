# cad-agent

Agent-driven mechanical CAD. Parametric parts in Python, deterministic gates,
headless renders, and an independent verifier. A harness: agents drive it from
the shell, and a design is done only when `cad verify` says so. Since step 6 it
scales to a machine: a library of real bought parts, projects linked as
sub-assemblies, rules for mass, heat and bending, and the files a shop needs.

```
bin/cad --help                                   # every command, and the exit codes
bin/cad --projects <dir> check <slug>            # run every gate
bin/cad --projects <dir> verify <slug>           # rebuild fresh, record the verdict with git
bin/cad --projects <dir> done <slug>             # the gate: exit 0 only if that verdict still stands
bin/cad --projects <dir> shop <slug>             # DXF, 3MF, STL, STEP, drawings and the BOM, for a design that is done
bin/cad lib ls                                   # the part library: rails, motors, extrusions, fasteners, with their sources
bin/cad serve [DIR ...]                          # the workbench: live 3D, drag parts, checks, activity
bin/cad pref [KEY [VALUE]]                       # preferences the commands use (MaxUndoSize, CacheLimit, ...)
bin/cad cache [--clear]                          # the user cache: location, size against CacheLimit
.venv/bin/python -m pytest tests -q              # 1553 tests
```

## Screenshots

The workbench: live 3D view of a design, with the part inspector and checks.

![Workbench](images/workbench-inspect.jpg)

An Arduino car designed by the agent (headless renders from `cad render`):

| Iso | Top |
|---|---|
| ![Arduino car, iso](images/arduino-car-iso.png) | ![Arduino car, top](images/arduino-car-top.png) |

## Install as a Claude Code plugin

In Claude Code:

```
/plugin marketplace add El-Guapo2024/cad-agent
/plugin install cad-agent@cad-agent
```

(or from a shell: `claude plugin marketplace add El-Guapo2024/cad-agent` then
`claude plugin install cad-agent@cad-agent`). The plugin brings the `cad` skill, the
`cad-reviewer` agent, the check-on-edit and done-on-stop hooks, and `/cad-agent:workbench`.
On the first session it installs the CLI and the CAD kernel (build123d, OCP, and ezdxf
and lib3mf for DXF and 3MF; a few hundred MB, a few minutes) into Claude Code's plugin data folder with `uv` if present,
else Python 3.12 to 3.14 (the kernel has no wheels for 3.15 yet), and puts `cad` on the
session's PATH. It then loads the kernel once
(`cad --version`, whose line it prints), so the first command is quick: on macOS the first
load of each native library is checked by the system, which can take minutes on a new
install and would otherwise be spent in your first `cad` call. Designs go to `./cad-projects`
in the project you open (set `CAD_PROJECTS` to change it). Check the manifest with
`claude plugin validate .`. Working inside this repo with the plugin also installed runs
the hooks twice; disable one of them there.

## The workbench

`bin/cad serve` opens a local page at http://127.0.0.1:8733 (or `--port`, or
`$PORT`), and the Claude app's Browser pane opens it too: the `workbench` entry
in `.claude/launch.json` lets the app pick a free port. It
is a client of the CLI: every scene, move, check and approval runs as a `cad`
command, so it shows up in the activity log next to what the agent ran. A click
never starts a process: the server sends each command to the warm worker's
socket itself, and the worker forks it.

**Always on (optional).** `bin/cad service install [DIR ...]` makes the workbench
a macOS login service (launchd). It stays up at http://127.0.0.1:8733 with the
kernel loaded, so opening it launches nothing and never waits on the 8–30 s
kernel import. The cost is about 400 MB held all the time. Point the app at it
with a launch entry that has only `"url"` and `"port"`, so the app attaches
instead of starting a server. `bin/cad service status` says whether it's up,
and `bin/cad service uninstall` removes it.

The 3D view is [three-cad-viewer](https://github.com/bernhard-42/three-cad-viewer)
(MIT, the viewer inside OCP CAD Viewer), fed by
[ocp-tessellate](https://pypi.org/project/ocp-tessellate/). The parts tree,
clipping with filled cuts, explode, measuring, views, zebra and studio
rendering all come from it. The workbench adds only what it lacks:

- **Live.** Edit a part (you or the agent) and the view rebuilds in a few
  seconds, keeping the camera and what you hid.
- **Move parts like Onshape.** Double-click a part to select it, turn on Move
  or Rotate, and drag the handle. It snaps to 1 mm and 15° by default. You can
  also type offsets, or undo with ⌘Z. Each move is written to
  `placements.toml`, and `cad place` answers right away with what the part now
  hits. A full `cad check` then runs in the background.
- **Edit dimensions.** The selected part's `PARAMS` show as fields. Change one
  and press Enter: `cad set` checks that the part still builds with the new
  value, writes that one literal into the part file (comments and layout
  stay, so git shows a one-number diff), and runs the part's gates. ⌘Z undoes
  it. Shape changes (a new hole, a fillet) are the agent's job in the Python.
- **Checks and activity.** Every gate row, the verdict and why `cad done`
  refuses, and a live feed of every `cad` command with its renders. Approving
  a render is a button, and it's your click.

Not carried over from the first version: the per-axis motion sliders.
three-cad-viewer has animation tracks for that, not wired up yet.

**Share a review.** `bin/cad page <slug>` writes a snapshot folder: a title block
with the verdict and commit, the model to turn, cut and measure, every gate row,
parts, and renders. Publish it as a private artifact and send the link. The
reader needs nothing installed, and nothing they do writes back to the design.

`placements.toml` is a design input. Every gate and `cad verify` see it, and git
shows exactly what moved. Fold settled moves into `assembly.py`
(`cad place <slug> <body> --reset` removes an entry).

Open a Claude Code session in this repo and it loads the harness from `.claude/`:
- the `/cad` skill, with the design loop
- a hook that runs `cad check` after every edit to a design file and feeds back what fails (a part
  edit also judges that part's bodies against the rest of the assembly)
- a stop hook that won't let a changed project go unverified without saying so
- the read-only `cad-reviewer` agent
- permission to run `bin/cad`

Each project states what it must do in `spec.toml` (envelope, clearances and how
far apart a pair may be, the size and position of a body, tool keep-outs, mass
budgets, bolt holes that must line up, how many holes a body has, how a shaft fits its
bores, hot zones, beam deflection, the axes and the
number of bodies a design must have, what goes to a shop), and the `spec` gate
checks every entry. A project without one is UNCHECKED. See
`cad_agent/spec.py` for the format (each section's own keys are in the docstring of
its module in `cad_agent/speckinds/`) and `tests/fixtures/*/spec.toml` for real
examples.

**The eval set.** `evals/` holds small design tasks, each a brief with a hidden
`spec.toml`, given parts and a reference design. `cad eval score <task> <dir>` verifies a
copy of a design with the given files and the hidden spec laid over it, and
`cad eval run --agent CMD` runs an agent on each task and scores what it leaves, so a change
to a rule, the skill or a hook shows up as a number. See `evals/README.md`.

Projects live wherever you keep them: `--projects DIR` or `CAD_PROJECTS`, or
`projects/` here by default. The first call starts a warm worker that imports
the CAD kernel once (20–35 s), then each command takes about a second;
`CAD_WARM=0` runs cold. The v2 plan, the research map behind it, and what is
built are in PLAN_V2.md. The MCP server it replaced was retired on 2026-09-28;
`python -m cad_agent` now runs the same CLI, cold.

### The FreeCAD-style UI (in progress)

`cad serve` also hosts a React version of the workbench at `/next/`
(http://localhost:8733/next/), laid out and styled after FreeCAD's development version (main, the code behind its weekly builds):
- the model tree and the property editor (Data/View tabs) on the left
- a Tasks tab for edits, with OK/Cancel
- the 3D view in the middle, with its navigation cube
- the report view, checks and console underneath, and a status bar

It behaves like FreeCAD too: hovering preselects, a click selects, the keys
0-6 pick standard views, V F fits all, Space toggles visibility and ⌘Z undoes.
Double-clicking a part opens its parameters. The console echoes every `cad`
command, the agent's and the UI's alike, and runs any `cad` command typed into
it, printing what a terminal would. The CAD Agent workbench (the default) puts
check, verify, done, cut list, tables, tool envelopes, bought parts, renders,
approvals and rules in its own menu and toolbar.

### Working together: a person in the UI, an agent in a terminal

Both drive the same project through the same CLI. Model changes (`cad set`,
`cad place`) land in the files, the workbench watches them, and the UI updates;
the person's edits in the UI run the same commands and show up in the activity
log. What only the UI has (the selection, what is hidden, colours, the camera)
is shared through `cad gui`, FreeCADGui's job:

    cad gui state PROJECT                    # what the person has selected, hidden, open
    cad gui select PROJECT post bracket.Face3
    cad gui hide PROJECT beam                # show / hide / clear likewise
    cad gui set PROJECT bracket ShapeColor=#ff0000 Transparency=50   # FreeCAD ViewObject names
    cad gui view PROJECT iso                 # front … iso, home, ortho, persp; `cad gui fit PROJECT`
    cad gui view PROJECT 'OrthographicCamera { position … orientation … height … }'   # an exact camera
    cad gui say PROJECT "look at the hinge"  # a line in the person's Report view
    cad gui commands PROJECT                 # the workbench's commands by FreeCAD name, and which are enabled
    cad gui run PROJECT Std_Placement        # run one, as Gui.runCommand does (opens the task for the person)

`cad gui state` also shows the camera the person is looking through, as
FreeCAD's View > Issue Camera Position prints it, so either side can save a
viewpoint and bring it back with `cad gui view`. `ShowPlacement=true` draws an
object's placement as an axis cross; `cad gui run PROJECT Part_EdgeSelection`
(or Vertex/Face, `Part_RemoveSelectionGate`) limits what the person can pick.

Visibility, colours and selectability persist in `out/gui.json` (FreeCAD keeps
them in GuiDocument.xml); `out/` is outside the verifier's source hash.

Undo is shared too, like a FreeCAD document's: every `cad set`, `cad place` and
bought-part change is journaled with who made it (`ui` or `agent`), Edit > Undo
in the UI and `cad undo PROJECT` in a terminal step back through the same list
(20 steps; `cad pref MaxUndoSize N` or Preferences > Document changes it), and `cad history PROJECT` shows it. Undo refuses when a file was
edited by hand since.

Macros are FreeCAD's, written in `cad` commands: Macro > Record Macro in the UI
records what the person does (model changes as `cad set`/`cad place` lines,
view and selection as `# cad gui …` comments unless Preferences > Macro says
otherwise) into `~/.cad-agent/macros/NAME.cad`. An agent reads one with `cad
macro show NAME` and replays it with `cad macro run NAME`; `cad macro save NAME
FILE` writes one for the person to run from Macro > Macros. `cad
gui` finds the running workbench that serves the project (each `cad serve`
registers itself in `~/.cad-agent/serve/`; `CAD_SERVE_URL` overrides) and exits
2 when none is running.

The source is in `ui/` (Vite, React, TypeScript, dockview, three-cad-viewer).
The build lands in `cad_agent/workbench/next/`, so running it needs no Node:

    cd ui && npm install && npm run build   # after changing ui/src
    npm run dev                              # live-reloading dev server on :5173, API proxied to :8733

Its colours and layout are ported from FreeCAD (LGPL-2.1-or-later: every file in
`ui/src` starts with an SPDX line, and the FreeCAD files each one follows, with
their copyright holders, are in its header and in `ui/NOTICE`), and its icons are
FreeCAD's for now (`ui/public/freecad-icons/README.md`). The licences of
everything the repo derives or ships are in `NOTICE` and `THIRD_PARTY_LICENSES`;
the build writes the notices of the npm packages in the bundle next to it
(`cad_agent/workbench/next/THIRD_PARTY_LICENSES.txt`).

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
  metal_render.py  GPU rasteriser via PyObjC Metal. Offscreen, no window; also the
                sidecar process the warm worker's forks draw through
  checks/fit.py every pair: interference volume or measured gap vs required
  checks/dfm.py per process: envelope, measured wall, in-plane web, feature count
  checks/web.py section a flat part, measure the material between its boundaries
  thickness.py  ray-cast wall thickness, so a part cannot declare its own
  runner.py     check_all writes checks.json; done_check is the gate
  buildcache.py a built part kept in <project>/.cad/cache for the edit loop (check, scene, measure,
                place); `cad verify` never reads it
  bought.py     vendor STEP or measured-with-a-source geometry, provenance enforced; the contract a bought
                part may declare (mass, material, max temperature, geometry, datum, sha256)
  bodies.py     what each body of an assembly is (BodyInfo) and the Assembly state.load_machine returns
  materials.py  density, stiffness, strength and service temperature, each with its source (FreeCAD cards or datasheets)
  cmdbase.py    the command contract: exit codes, Result, the argument helpers, and the commands built later
  registry.py   the registries: Row, scopes, @register for checks and @spec_kind for spec.toml sections
  rules.py      the checks written before step 6, registered. The list of what a run verifies
  ruleset/      one module per rule from step 6 on; rules.py imports them all
  speckinds/    one module per section of spec.toml (twelve), and kit.py for what a kind uses
  library/      the part library: catalog.toml, the generators (gen/), the user's store, `cad lib`
  subassembly.py a machine made of sibling projects, and the poses it can be put in
  beam.py       Euler-Bernoulli bending and the cross-sections of a solid, for [[deflection]]
  checks/visual.py  render drift against approved baselines, with diff images
  cutlist.py    stock derived from each part's CUTLIST, roughly priced
  export.py     STEP for a shop (the same bytes on every run), STL and 3MF for a printer, DXF for a laser
  dxf.py        a laser part's outline as a DXF, written the way FreeCAD writes one and read back by ezdxf
  threemf.py    a printed part's mesh as a 3MF and an STL, the same bytes every run, read back
  bom.py        the bill of materials: FreeCAD's Assembly_CreateBom plus what a shop needs
  shop.py       cad shop: out/shop/ for a design that is done, with a manifest of hashes
  drawing/      cad drawing: a dimensioned sheet of a plate (hidden line removal, DXF master, SVG and PDF)
  cli.py        the cad CLI: every command, --json, exit codes, activity log
  warm.py       the warm worker: kernel imported once, a fresh fork per command, plus the Metal sidecar
  verify.py     the verifier: fresh rebuild, source and engine hashes, git, cad done
  spec.py       spec.toml, the brief as acceptance tests
  evals.py      cad eval: design tasks (evals/) scored through cad verify, no kernel of its own
  placements.py placements.toml: parts moved by hand, applied under every gate
  scene.py      out/scene.json: ocp-tessellate data for the viewer, plus moves, axes, masses
  serve.py      cad serve: the workbench server, live events, CLI-backed actions
  service.py    cad service: the workbench as a macOS login service, kernel kept warm
  page.py       cad page: a review snapshot to publish as an artifact
  workbench/    the pages on three-cad-viewer: workbench (index.html, app.js),
                review page (page.html, page.js), its stylesheet (vendor/)
.claude/        the /cad skill, the check and stop hooks, the cad-reviewer agent, launch.json
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

**Metal in the warm worker.** Its commands run in forks, and a fork cannot
compile a Metal shader: the compiler is an XPC service, and XPC does not work
in a process that was forked and not exec'd. The compile only succeeded when
Metal's on-disk shader cache already held this shader for this python (a cold
run fills it; another venv's python does not share it), so a venv that had
once rendered cold looked fine and a fresh install fell back to numpy. So the
worker execs a sidecar (`python -m cad_agent.metal_render
_serve`) that owns the device and does every draw; a fork sends it its
triangles over a socket (`CAD_METAL_SIDECAR`) and gets pixels identical to a
cold render's. `cad warm status` shows it. The worker restarts itself, sidecar
included, when `metal_render.py`, `render.py`, `warm.py` or the preloaded kernel
changes on disk (it checks before every command, so no command runs on old code
under the engine hash of the new); a worker started before that check needs one
`cad warm stop`.

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

A bought part may also declare what the rules for mass, heat and stiffness read:
`mass_g` and where it came from, `material`, `max_temp_c` and its datasheet, `geometry`
(`exact` or `envelope`, the default: only an exact part may give stiffness), a `datum`
that puts the vendor's origin where the part's own frame is, and the `sha256` of the
file, which the provenance rule checks. `cad_agent/bought.py` documents the keys. Nothing
is defaulted to look measured: a mass with no source is not used.

A STEP carries its donor assembly's coordinates, so an assembly must
re-origin bought geometry rather than assume it is centred. The SK-Cube
bracket in the first project lands at (-270.8, -541.0, 171.5).

## The part library

A machine is made of parts nobody here draws: rails, motors, extrusions, bearings,
fasteners. `cad lib` is where a design gets them, with their numbers and where each
number came from, so the mass, the temperature rating and the stiffness the rules read
are not remembered either.

```
cad lib ls [QUERY] [--kind generator|step|bd_warehouse]   what the library holds, and what is ready to use
cad lib info <entry>                         vendor, part number, licence, every dimension with its source, mass, rating
cad lib use <slug> <entry> [KEY=VALUE ...]   copy it into the project's bought/ (--as NAME, --replace)
cad lib add <entry> FILE --source URL        keep a STEP you downloaded in your own store
cad lib fetch <entry> ...                    download a STEP where its licence allows it
cad lib check [<slug>]                       hashes: the store against the catalog, or a project's bought/ against its sidecars
```

The catalog (`cad_agent/library/catalog.toml`) ships 22 entries. Every number sits beside
the page it came from, and a number no source gives is not in it: what needs that number
is UNCHECKED, by design.

| Entry | What it is |
|---|---|
| `mgn12-rail`, `mgn12c`, `mgn12h`, `mgn15-rail`, `mgn15c`, `mgn15h` | HIWIN MGN rails (they take a `length`) and carriages, drawn from the maker's catalog tables. Envelopes: no balls, end caps or seals |
| `extrusion-2020`, `-2040`, `-4040`, and each with `-envelope` | Framing Tech T-slot profiles. The profiles have the real slot section and are `exact` (area and second moment within 1 % of the maker's STEP), so a stiffness rule may stand on them. The envelope ones are a plain box |
| `nema17`, `nema8` | Novanta IMS and Nanotec motors, with the maker's mass (the NEMA 17 takes a `length`) |
| `gt2-idler-20t` | a smooth 20-tooth idler drawn from retailer listings, since no maker publishes a drawing: marked unverified |
| `fcl-608zz`, `fcl-623zz`, `fcl-gt2-idler-20t`, `fcl-nema17` | four STEP files from the FreeCAD-library (CC-BY 3.0), pinned by URL and sha256. Community models: marked unverified |
| `iso4762-screw`, `iso4032-nut`, `iso7089-washer` | ISO fasteners drawn by bd_warehouse (Apache-2.0). They need `pip install 'cad-agent[fasteners]'` (in the plugin's Python for a plugin install) |

**Where vendor files live.** A vendor's STEP is never in the repo. The store is a folder
of yours, `$CAD_LIBRARY` or `~/.cad-agent/library` (it can be a private repository your
team shares): `<sha256>.step` for each file and `library.json` for your own entries and
how each file came to be there. `fetch` downloads a file into it only where the licence
lets the repo do that (CC-BY and the like, with the credit carried into the sidecar) and
checks it against the catalog's sha256. For any other licence, download it by hand and run
`lib add <entry> FILE --source URL`, which checks the same pin. A file that does not hash
to its pin is refused and written nowhere.

**What `use` writes.** A generator or bd_warehouse entry becomes a small module in
`bought/` that holds every number its part was built from. A STEP entry becomes the file.
Beside it goes a sidecar: library, source, vendor, pn, licence, attribution, `mass_g` with
its `mass_source` (for the length you asked for: a 300 mm rail is not a 150 mm one),
material, `max_temp_c` with its source, geometry, datum and sha256. The module is pinned by
that hash, so editing it by hand is a FAIL row (`lib use --replace` writes it again); a part
that declares something unconfirmed is left unpinned, because `cad bought verify` rewrites it
when you record a calliper reading. The change is journaled, so `cad undo` takes it back
(copies of 4 MiB or more are not journaled, and the command says so).

After that the project is on its own. `cad verify`, the build cache, CI and the eval scorer
read the project's tree and never the store or the catalog, so a verdict does not move when
the library does. The generators are code in `cad_agent/library/gen/`, which is part of the
engine hash: a change to a generator changes the verdicts of every project that uses it, as a
change to a rule does. `lib check <slug>` re-hashes the copies and says when the catalog has
moved on since.

What the entries declare: the two motors give the maker's ambient limit as `max_temp_c`
(40 C and 50 C), so a `[[heat]]` zone above that around a motor is a FAIL, which is the maker's
rating and not a bug. The rails and carriages declare no rating, because no source gives one for
the standard block, so a hot zone near one is UNCHECKED; the extrusions are rated as the
aluminium they are. Only the extrusion profiles are `exact`.

## A machine: sub-assemblies, poses and axes

A machine is too big for one assembly.py. The gantry is a design of its own, with its parts,
its gates and its own `cad verify`. The machine says where it stands, and the two are judged
together. This is FreeCAD's link to another document (`Assembly::AssemblyLink`).

```python
SUBASSEMBLIES = {"gantry": {"project": "gantry", "at": [0, 0, 120], "turn": [0, 0, 90]}}
POSES = {"park": {"gantry/x": -150, "gantry/y": 0}}
AXES = {"z": {"moves": ("gantry/*",), "direction": (0, 0, 1), "travel": (0, 50), "work": (0, 40)}}
```

**The declaration.** The key is the instance's name and the prefix of its bodies, so one
project can be placed twice (`z_left`, `z_right`). `project` is a folder next to the
machine's under the projects root: a name, never a path. `at` (mm) and `turn` (degrees,
Rx.Ry.Rz about the child's own origin) are a rigid move of the child's whole frame,
`Pos(*at) * Rot(*turn)`, which is what placements.toml means by a move. There is no mirror
and no scale: `mirror()` drops what a body is.

**What flattening does.** Bodies are named `gantry/x_carriage`; a child's own children nest
(`gantry/pulley/belt`). The child's CLEARANCE and ALLOW_CONTACT come in with both names
prefixed (the machine's own entry for a pair wins). Its AXES come in as `gantry/x`, with
direction and tool point turned by the instance (travel and work are distances and stay),
and its POSES as `gantry/park`. The machine may list `"gantry/*"` in an axis's `moves`: every
body under that instance. Its own `placements.toml` may move a child's body by its full name
(`cad place machine gantry/x_carriage ...`); the child's own placements.toml always applies.

**What stays the child's.** Each child is a full project: `cad check gantry` and
`cad verify gantry` work on it alone, and a design that is not done on its own does not become
done by being linked.
- The machine's `cad check` runs every gate of every project in the tree, each as
  `cad check <child>` runs it, and reports their rows as `<project>:<check>/<rule>`.
- The machine's `cad verify` rebuilds all of it from source in one fresh process. It never
  reads a child's verify.json or checks.json, which are claims and not evidence. Its
  `source_hash` and git record cover every project below it (`children`, and `tree` in
  verify.json).
- The machine is not done until every child is: each needs a spec.toml (without one the row is
  `<project>:spec/present`) and its approved renders (`cad approve <project>`).
- Project names in SUBASSEMBLIES must be string literals, because verify finds the tree by
  reading assembly.py and running nothing. A name it cannot read leaves the verdict UNCHECKED.
- Cost, measured with simple parts: `verify` takes 2.0 s for 20 bodies (a machine of 6 and two
  sub-assemblies of 7) against 1.1 s for the same bodies in one project, and 11 to 13 s against
  6 to 7 s for 80. The pairs inside a child are measured in its own check and again in the
  machine's. A machine of heavy STEP bodies costs more for each pair.

**Failures** are FAIL rows `subassembly/<kind>`, never a crash, all listed at once (exit 1):
`cycle` (a project is its own ancestor; the chain is in the row), `depth` (more than 8
levels), `name` (a "/" in a body or instance name that is not the prefix of a sub-assembly's
bodies, or a body with an instance's name), `project` (it does not exist or has no
assembly.py), `build` (its assembly.py or a part raised), `declaration` (not
`{project, at, turn}`, or an `at` or `turn` that is not three numbers), `moves` ("gantry/*"
with no such instance or no bodies). Each linked instance also gets a PASS row
`subassembly/linked`.

**Shop files.** The machine's `cad shop` makes files for its own parts only, and its BOM lists a
child's parts nested under the child. A child's parts are cut and drawn from the child
(`cad shop gantry`, once that project is done itself; `cad drawing gantry plate`).
`subassembly.file_stem` turns `gantry/x_carriage` into `gantry__x_carriage` wherever a file is
named after a body.

**Poses.** A pose is `{axis: mm}` from home, inside the axis's travel. `pose = "park"` on a
`[[clearance]]`, `[[keepout]]` or `[[position]]` judges that entry with the machine there; the
row says `at pose park`. The `poses` rule checks every declared pose: its axes are declared,
each position is inside travel, the bodies the axes move exist. A spec entry that names a pose
in a section that does not read one (anything but those three) is UNCHECKED. `sweep` still
drives each axis alone from home, so a pose is the only place two axes are off home together,
at the positions someone named. `cad render` and the workbench show home.

**`[[axis]]` and `[bodies]`.** A design that declared no AXES was judged at home and passed the
sweep and reach rules by having nothing to judge, and "exactly six bodies, called ..." in a brief
was held by nothing. `[[axis]] name = "x"` requires the axis to exist, and its other keys say what
it must do: `moves` (at least these bodies; exactly these with `only = true`), `direction` (a line,
either way, within `tol_deg`, default 1), `travel_min_mm` and `travel_max_mm`, `work_min_mm`
(a work span at least that long), `tool` (the body that carries its tool point). Whether the work
span lies inside the travel is `reach`'s and whether the travel is clear is `sweep`'s. `[bodies]`
takes `count` and/or `names`. Both are FAIL when the design does not do what was asked, and
UNCHECKED when the entry cannot be read (a body that is not there, a direction of zero length, no
assembly).

`tests/fixtures/mini_machine` is a regression machine that uses every piece of this section and the
two after it; CI runs `cad verify` on it like on every folder of `tests/fixtures`.

## Mass, heat and deflection

These rules read what a body is. `bodies.py` gives every body of an assembly a `BodyInfo`:
`made` (a part module), `bought` (from `bought/`) or `stock` (anything else assembly.py builds;
it has no material, so no mass and no rating). A made body weighs volume times density of its
MATERIAL and is rated for the service temperature `materials.py` gives that material. A bought
body weighs the `mass_g` it declares with a `mass_source`, and is rated for the `max_temp_c` it
declares with a `max_temp_source`, else for its declared `material`. Geometry is `exact` for a
made body and for a bought part only if it says so. No rule fills a gap with a default: a number
nobody states is unknown, and the row is UNCHECKED, naming the body and what it lacks.

**Materials** (`cad tables materials`) has 12 materials with density, Young's modulus, Poisson's
ratio, yield strength and service temperature, each with the FreeCAD card or datasheet it came
from. Five of the cards are CC-BY-3.0, so their credit (author, licence URL, where the card is)
is printed with their values: `credit` in each row, `credits` in `cad tables`, and in the E of a
`[[deflection]]` row. FreeCAD's cards have no service temperature, so that number is ours, with its basis: heat
deflection temperature at 0.45 MPa (ISO 75-2 B) for the thermoplastics, the glass transition for
polyimide, and a stated service limit for acrylic, FR4 and the metals (MakeItFrom.com's "Maximum
Temperature: Mechanical" for the alloy the table stands for). At 250 C only steel (400),
stainless (710) and polyimide (360) are rated; aluminium (170), brass (120), copper (200) and every
printed plastic are not. PC and ASA are not in the table (adding them would move the pinned
densities): a bought part declares its own `max_temp_c`. The densities are the ones `geom.DENSITY`
always had, and every mass row rests on them; where a FreeCAD card says otherwise the old value
stays and a datasheet is its source. Some FreeCAD cards are CC-BY-3.0, and `materials.CARDS`
credits each author.

**`[[mass]]`** has three forms, one to an entry. `parts = { x_carriage = 1 }` counts part modules
as built, which is blind to anything assembly.py does to them. `bodies = [...]` weighs the placed
bodies as assembly.py holds them, so a part cut there weighs what is left. `moving = "x"` weighs
every body `AXES["x"]` moves. A body of unknown mass makes the row UNCHECKED, naming each one,
with one exception that is a proof and not a guess: if the bodies whose mass is known already weigh
more than `max_g`, the row is FAIL.

**`com`** answers what `stance` says it does not: that the weight is over the footprint. The
assembly stands on its lowest plane. The footprint is the support polygon, the convex hull of
everything within 0.05 mm of that plane (not the bounding box of the bodies that touch). The centre
of mass is the mass-weighted mean of the bodies' centroids, and it must lie inside. Then, for each
axis, the same at both ends of its travel, one axis at a time: the centre moves by (mass moved /
total mass) times the travel, so a gantry that is stable at home and tips with its carriage at the
end is a FAIL there. An axis that moves a body standing on the ground changes the footprint as it
goes, which this does not model: UNCHECKED. The rule is N/A until a bought part declares a mass, and
strict from then on (UNCHECKED while any body has none). The 13 designs of before step 6 each hold a
body of unknown mass, and putting them all on hold for a claim none made would have been wrong.

**`[[heat]]`**: `source` (a body) or `at` (a point), `temp_c`, `radius_mm`, optional `margin_c` and
`clear`. Every other body within `radius_mm` of the source needs a rating of at least
`temp_c + margin_c`. The distance is the exact B-rep distance, the way `[[clearance]]` measures a
gap, and a body that overlaps the source is at distance 0, so it is inside. The source is exempt:
it makes the heat. `clear` lists bodies that must stay outside the zone however well rated, or
`"all"`: PASS outside, FAIL inside. A rating below the need is a FAIL. These are UNCHECKED: a body in
the zone with no rating (no MATERIAL, a material the table does not list, a bought part with
neither `max_temp_c` nor a material, a stock body), a source that is not a body, a missing or
unknown key. An entry with no body in its zone gives one PASS row saying so.

Every row says "a zone, not a thermal model". Nothing conducts, radiates or cools: a body at the
edge is judged as hot as one touching the source, and inside the radius an air gap, an insulating
standoff or a heat sink buys nothing here. A heat deflection temperature is not a life rating, so
`margin_c` is how a design asks for headroom the table does not have.

**`[[deflection]]`**: `body`, `support` (`simple`, `fixed` or `cantilever`), `span_mm` (default the
body's length), one load (`load_n`, `load_g`, or `load_moving` = the mass an axis moves; `self_weight`
alone is a load too), `at` (`center`, `end` or `worst`, the default), `max_um`, `direction` (default
`"-z"`; a sign is allowed and ignored), `axis` (which way the beam runs, when it is not clearly
longest along one), `solid`.

The method is Euler-Bernoulli superposition from Roark's Table 8.1 (the case ids were checked against
two open transcriptions of the table, not the book). E comes from `materials.py` with the source it
cites. The second moment of area comes from the body's own cross-sections: a plane across the beam
cuts the solid (`BRepAlgoAPI_Common`) and `BRepGProp` gives the face's moments, as FreeCAD's
`Face.MatrixOfInertia` does. The sections are the middle of 21 equal cells, a little way in from both
ends, and the middle of every cut across the beam, so a 2 mm notch is not missed. The rule PASSes when the weakest section the
whole way gives no more than `max_um`, FAILs when the stiffest section the whole way gives more, and
is UNCHECKED between the two, because then the answer depends on a section it cannot choose.

UNCHECKED, with its reason, and never a guess:
- the geometry is an envelope: stock built in assembly.py, or a bought part not declared
  `geometry = "exact"` (or one whose dimensions are unverified);
- the body is a solid box of a 2020, 2040 or 4040's outer size. That is what `extrusion_blank`
  makes, drilled or not, and a real profile has about half the stiffness of the solid. It is
  recognised by what it is (at least twice as long as its longer side, 90 % or more of the
  footprint filled), not by a tag. Judge the library's real profile, or say `solid = true` if the part
  really is a bar (the row then says it took the entry's word). A box of another size is judged as
  the solid bar it is;
- no MATERIAL, or no Young's modulus with a source for it;
- a mass it needs is unknown (`load_moving` adds the masses of the bodies the axis moves, the beam
  itself left out; `self_weight` uses the body's own);
- the body is not a beam: not one solid, not clearly longest along one axis, a long edge tilted or
  bent, a section cut through or in pieces over a long run, more than 120 stations;
- span/depth is under 10 for simple and cantilever beams, 20 for fixed ends, where shear matters and
  Euler-Bernoulli leaves it out;
- the load acts along the beam's own axis.

Not modelled: torsion (the load is taken through the section's centre, so an open section such as a
channel or an angle will twist), buckling, the local give of a load or a support, creep, and the
anisotropy of a printed part. Supports are ideal. A T-slot body costs about 1.5 s a run, since it is
cut once and every entry that names it shares the cuts. The closed forms are held against
textbook cases and a finite-element beam that shares no coefficient with them, the bounds on beams
whose stiffness changes at random, and a T-slot against its datasheet. A finite-element cross-check
(CalculiX with Gmsh) was planned as an optional second opinion and is not built.

## Files for a shop

```
cad export <slug> <part> --format step|stl|3mf|dxf
cad bom <slug> [--only-parts] [--flat]
cad shop <slug> [--draft | --check] [--all]
cad drawing <slug> <part> [--angle first|third] [--format dxf,svg,pdf] [--sheet A4..A0|auto] [--scale 1:1..|auto] [--out DIR] [--all]
```

**The bytes.** A hash in a manifest rests on every file being the same bytes whenever and wherever
it is made. STL, 3MF, DXF and the BOM files are, on either kernel (OCCT 7.9 and 8.0). A STEP is too,
but for one header line that names the OCCT that wrote it, which is true and is left alone;
`--check` compares a STEP without it. The STEP's time stamp is pinned and its occurrence numbers are
counted from 1. STL and 3MF are one mesh of sorted integers (the 3MF a zip written by hand, stored,
with a fixed time stamp, because lib3mf has no wheel for Linux on aarch64 and its writer's choices
would put the library's version in the bytes; lib3mf reads the file back instead). The DXF is
written by hand at release 14, with FreeCAD's ImpExpDxf defaults, on a nanometre grid, holes first
and the outline last. A part's DXF is the section by the plane half way through its thickness, in the
part's own frame, in millimetres.

**`cad export`** writes the file you ask for into `out/<part>.<format>` and judges none of it: a DXF
of a wheel is the wheel's mid-plane section. The rules below belong to `shop`.

**`cad bom`** ports FreeCAD's `Assembly_CreateBom`. Its columns come first and in its order (Index,
Name, Description, File Name, Quantity); the index is hierarchical, and a quantity folds the same
things together. It adds Kind (made, bought, stock or assembly), Material, Process, Vendor, PN,
Licence, Source, Mass (g) with its source, Shop file, Bodies and Notes. Two bodies are one line when
they are the same kind from the same part and the same shape (volume and area to a millionth, the
same faces) wherever they stand. A mirrored body has lost what it was, so it joins the made or
bought line of its shape and name stem and says so in Notes. A mass is never filled in: the word is
`unknown`, and the totals say how many bodies they leave out. `--only-parts` keeps the made parts and
sub-assemblies (FreeCAD's "Only parts" keeps part containers and drops solids, another cut under the same
name); `--flat` turns off its detailed sub-assemblies. It writes
`out/bom.csv` and `out/bom.json`, and never exits 2: it judges nothing.

**`cad shop`** writes `out/shop/` for the parts this project makes:

| File | For |
|---|---|
| `<part>.step` | every made part |
| `<part>.dxf` | a `laser_cut` part |
| `<part>.3mf`, `<part>.stl` | an `fdm` part |
| `drawings/<part>.dxf`, `.svg`, `.pdf` | each cnc and laser_cut part that is a plate `cad drawing` can show |
| `bom.csv`, `bom.json` | the whole design |
| `manifest.json` | each file's sha256 and size, the commit, the verdict, the rows, the drawings that were skipped |

A file that goes to a shop is one a person may cut or print without looking, so the command is
fenced:
- It exits 2 and writes nothing unless `cad done` holds: the last `cad verify` passed in a fresh
  process, on these files and these rules, on committed work. The manifest records that commit and
  the one at HEAD.
- Parts are built from source, never from the build cache.
- The rules of a made part run on what is about to be written. A row that is not PASS or N/A stops
  it, with nothing written (FAIL exits 1, UNCHECKED exits 2), so a folder from an earlier run is
  never half replaced.
- `--draft` writes whatever there is, with NOT VERIFIED inside every file where the format has room
  (the DXF's comment and a text on layer `NOT_VERIFIED`, the 3MF's title and description, the STL's
  header, the STEP's description, a Status column in bom.csv, `draft: true` in the manifest). It
  exits as the rows say, and 2 for a design that is not done.
- `--check` writes nothing. It regenerates and compares with out/shop/ file by file by sha256 and
  lists what is `missing`, `edited`, `stale`, `new`, `gone` or `extra`. Exit 0 when nothing differs,
  1 when something does, 2 when it cannot say (no out/shop/, a draft folder, a design that is not
  done).

**`[shop]` and the part rules.** A spec with a `[shop]` table (an empty one is enough) says the
design goes to a shop. From then on `cad check` and `cad verify` run these on every part, and a
design without the table is not held to them:
- `shop/laser through-cut` (a `laser_cut` part): every face is an end plane or runs along the
  thickness. A pocket, a step, a chamfer, a countersink, a draft or a cross hole is a FAIL.
- `shop/dxf readback`: ezdxf reads the DXF back and it equals the mid-plane section within 0.001 mm,
  entity for entity and in millimetres.
- `shop/3mf watertight` (an `fdm` part): the 3MF reads back closed, manifold and wound one way round
  (by lib3mf, or the built-in reader where lib3mf is not installed, and the row says so).
- `shop/3mf volume`: its volume is the solid's within 0.5 %.
- `shop file` for every made body: the part module the file is made from builds this body. A body
  assembly.py cuts, or builds with other parameters, would be made wrong, and that is a FAIL.

The table's keys are judged against the BOM `cad bom` writes: `bom = { wheel = 2 }` (the quantity of a
line, or of a body's line; 0 says it must not be there), `orderable = true` (each bought line has a
vendor and a part number: UNCHECKED naming what it lacks), `mass = "known"` (each line has a mass with
its source: UNCHECKED naming the lines without), `files = [...]` (each must be a file `cad shop` makes
for this BOM, else FAIL naming the part's process). A file under `drawings/` in `files` is UNCHECKED:
the BOM cannot say which plates will be drawn. Anything a rule cannot measure is UNCHECKED, never PASS.

**`cad drawing`** is a port of what TechDraw does for a plate: hidden-line removal with OCCT's
`HLRBRep_Algo` (visible edges solid, hidden ones dashed, and the visible smooth edges where two faces
meet tangent thin, as TechDraw draws them by default), first angle projection by default
(ISO 128-30, TechDraw's default) or `--angle third`, an ISO 5457 frame (without the zone grid),
and the plate's sizes from its B-rep: overall size, the position of every hole, slot and window from
the lower-left corner, a letter and a callout for each size of cutout, and the general tolerance of
ISO 2768-m. A size that standard has no tolerance for (under 0.5 mm, over 4000 mm) is drawn with a
note saying so. The title block carries the part, project, material, process, scale, sheet, projection
and commit, and NOT VERIFIED in red and in a banner unless `cad done` holds. The DXF is the master
(layers FRAME, MARKS, TITLE, VISIBLE, HIDDEN, CENTRE, DIMENSION, DIM_ORD, DIM_TEXT, TEXT,
NOT_VERIFIED); the SVG and the PDF are drawn from what ezdxf reads in it, by code of this repo and no
library.

It draws a prism along its thinnest axis: a rectangular outline with equal corner radii, round holes,
slots and rectangular windows, all the way through. Nothing else is drawn, and nothing is written for
it: no sections, no GD&T, no tolerance but the general one, no threads, countersinks, counterbores,
sheet metal or printed parts. A wrong drawing is worse than none. Of the eval reference designs it
draws `laser_panel/panel` and `nema17_mount/bracket`; `galvo_mount`, `pinned_carrier` and
`hotplate_standoffs` have pockets or cross holes (exit 2, with the reason), and the rest are printed
(exit 3). Every drawing is judged before it is written: the
plate the printed numbers describe equals the solid's end face, the DXF read back by ezdxf draws that
plate at its stated scale with each dimension at the length its number says, no two labels overlap, and
the SVG and PDF have an element for each entity of the DXF. A plate takes 75 to 180 ms, and 0.7 s with
40 holes.

**Exit codes of the step 6 commands**, on top of the usual 0 ok, 1 FAIL, 2 UNCHECKED, 3 usage, 4 crash:

| Command | 1 | 2 | 3 |
|---|---|---|---|
| `lib ls`, `lib info` | | | an unknown entry |
| `lib use` | a file is not the one pinned | | an unknown project, entry or parameter; a name taken; bd_warehouse not installed |
| `lib add` | the file is not the pin | | not a STEP; no `--source`; a bad name |
| `lib fetch` | the download does not hash to the pin | the network did not answer | no URL, no pin, or a licence that does not allow it |
| `lib check` | any FAIL row (a store file, a pinned copy that changed) | any UNCHECKED row | an unknown project |
| `export` | the part did not build | | an unknown part or format |
| `bom` | the project did not build | never | an unknown project |
| `shop` | a row FAIL; `--check` found a difference | not done; a row UNCHECKED; `--draft` unless done and clean; nothing to check | an unknown project; `--draft` with `--check` |
| `drawing` | a gate FAIL; the part did not build | drawn but NOT VERIFIED; not a plate; a row unsettled | a printed part, no PROCESS, a "/" in the part name, a bad option |

## Adding a check is one function

Checks register themselves. The runner discovers them, the gate consumes them,
and the report prints them, with no other edit. The ones written first are in
`rules.py`; a new one is a file in `cad_agent/ruleset/`, which `rules.py` imports
whole:

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

A section of `spec.toml` is added the same way: a function registered with
`@spec_kind("heat")` in its own module of `cad_agent/speckinds/` judges one entry
and yields rows (`speckinds/kit.py` has the helpers), and `spec.py` runs whatever is
registered. A section nobody registered is UNCHECKED. The commands of step 6 (`lib`,
`bom`, `shop`, `drawing`) are rows in `cmdbase.LAZY`: they are listed and parsed at once, and
the module that handles one is imported only when the command runs, so `cad --help` and
`cad lib ls` do not wait for the kernel. A command whose module is missing answers exit 3
"not built yet".

Shipped checks:

| Check | Scope | Verifies |
|---|---|---|
| `geometry` | part | envelope, measured wall, in-plane web, feature count |
| `visual` | part | silhouette coverage, drift from the approved render, drawn extent |
| `shop` | part | a laser part is a through-cut its DXF reads back to; a printed part's 3MF is closed and has the solid's volume (only with `[shop]`) |
| `subassembly` | assembly | each sub-assembly is linked as declared; no "/" in a body's name that no sub-assembly explains |
| `placements` | assembly | which bodies were moved by hand; an entry for a missing body is UNCHECKED |
| `fit` | assembly | interference and clearance, every pair |
| `sweep`, `reach` | assembly | each declared axis swept through its travel; the tool point covers the work span |
| `poses` | assembly | every pose in POSES drives declared axes inside their travel; no spec entry names a pose it ignores |
| `stance` | assembly | footprint area at the contact plane |
| `com` | assembly | the centre of mass is over the footprint, at home and at the ends of each axis (once a bought part declares a mass) |
| `spec` | assembly | every requirement in spec.toml |
| `provenance` | project | whether each bought part records, and confirms, its source, its declared keys and its hash |

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
anonymous feature index cannot be acted on. A flat part with no cutout has no
web, so the rule is N/A for a plain plate or lid; its feature count is still
held to the `EXPECT_FEATURES` the part declares (0 for a plain one). A slice
that cuts no material is different: the outline could not be read, so that
stays UNCHECKED.

## The gates fail, they do not report

`done_check` returns `ok:false` on any FAIL **and** on any UNCHECKED. A wall
thickness that was never measured is not a pass. This is deliberate: an
unreviewed finding that joins a pile is a finding nobody acts on.

`N/A` is distinct from a pass: it marks a rule that does not apply, such as
the in-plane web rule on a chunky part or on a flat one with no cutout.

## First project

`projects/desk_fab_line` — the two-cell Desk Fab Line. Built so far: the
reflow hot plate and its ceramic standoffs, docked over 2040 floor rails,
with the plate-to-frame air gap gated at 20 mm. The plate takes either a flat
mica element underneath or two cartridge bores, chosen by a parameter, because
which heater to buy is still open.

`done_check` is deliberately red on this project: the mica heater's dimensions
came from no published drawing, and the gate holds the project open until they
are confirmed. Geometry and manufacturability are green.
