---
name: cad
description: Design mechanical parts, assemblies and machines with the cad-agent CLI (build123d). Write parametric part modules, an assembly and a spec.toml, run the gates, look at renders, and finish only when `cad verify` then `cad done` pass. Use for any 3D mechanical design task in this repo, or when the user says "design a part", "bracket", "mount", "enclosure", "gantry", "machine", "bill of materials", or asks to check, verify or render a cad project, or for files for a shop (DXF, 3MF, STL, STEP, drawings).
---

# Mechanical design with `cad`

**One brief, one autonomous run, one report.** Infer what the brief leaves out
from engineering norms, write the assumptions down, and run. Ask only when going
on would be unsafe or useless.

Everything runs through the CLI: `bin/cad` from the repo root, or plain `cad` when
cad-agent is installed as a Claude Code plugin (the commands below are the same;
`cad --help` lists every command and the exit codes). As a plugin, designs live in
`./cad-projects` of the project you're working in (`CAD_PROJECTS`). Point it at a projects directory with
`--projects DIR` or `CAD_PROJECTS`. The exit code is the verdict: 0 pass,
1 FAIL, 2 UNCHECKED, 3 bad arguments, 4 a cad-agent crash. Add `--json` for
output to parse.

This file is the short version. `docs/DETAILS.md` (three folders up from here, in the
checkout or the plugin) has the rest: every key of every spec section, every case a
rule calls UNCHECKED, the exit codes of each command. The format of a spec section is
also the docstring of `cad_agent/speckinds/<section>.py`.

## The boundary

**You specify. The kernel computes. The verifier decides. The human fabricates.**

- Never state a dimension a command could measure. Quote `cad` output.
- Never draw a diagram. Renders come from the same geometry the gates judged.
- Never decide a design is done. `cad done` decides.

## The loop

```
bin/cad init <slug> --brief "..."             # new project
# write spec.toml first: what the design must do (below)
bin/cad lib ls                                # bought parts the library has; `lib use <slug> <entry>` copies one in
# write parts/<name>.py, then assembly.py
bin/cad check <slug> --part <name>            # fast loop: the part's rules, and its bodies' fit against the rest
bin/cad build <slug> <name> --set t=5         # sweep a value without editing the file
bin/cad render <slug> [<name>] --view iso     # prints a PNG path: Read it and look
bin/cad measure <slug> <a> <b> --posed        # the raw fit query between placed bodies
bin/cad check <slug>                          # every gate, including the spec
git commit                                    # the verifier only counts committed work
bin/cad verify <slug>                         # fresh rebuild; verdict tied to the commit
bin/cad done <slug>                           # exit 0 only if that verdict still stands
bin/cad shop <slug>                           # files for a shop, only for a design that is done (below)
```

A hook runs `cad check` after every edit to a part, assembly or spec, and hands
back what fails. A stop hook will not let you finish over a changed project
that `cad done` rejects. Fix what they name, or say plainly that the design is
not done and why.

`check`, `scene`, `measure` and `place` rebuild only the parts that changed: a built
part is kept under the project's `.cad/cache` and read back while it and everything
it imports are as they were (`--no-cache` rebuilds all). That is why a part edit can
also show `interference` or `clearance` rows against its neighbours straight away.
`cad verify` never reads that cache: it rebuilds everything from source.

## Write the spec first

`spec.toml` is the brief as acceptance tests, and a project without one can't
pass. Write what the design must do, in terms the kernel can measure:

```toml
[envelope]                  # the whole assembly's bounding box
max_mm = [560, 450, 200]

[[clearance]]               # a gap two placed bodies must keep
a = "x_carriage"
b = "gantry_end_left"
min_mm = 3.0                # min_mm and/or max_mm; max_mm = 0.3 is how "must grip" is written
pose = "park"               # optional, here and on position and keepout: judged with the machine at that pose

[[size]]                    # a placed body's own bounding box (min_mm and/or max_mm)
body = "pump"               # holds a given part to its real size
min_mm = [60, 40, 25]
max_mm = [61, 41, 26]

[[position]]                # where a placed body's bounding-box center must be
body = "pump"
center_mm = [0, 0, 20]
tol_mm = 0.1                # default

[[keepout]]                 # a tool volume listed bodies must avoid
tool = "laser_cone"         # drill, end_mill, collet_nose, laser_cone, needle
params = { focal_length = 210, field = 150, lens_dia = 30 }
at = [0, 0, 0]
clear = ["gantry_beam"]     # or "all"

[[mass]]                    # a weight budget over part modules,
parts = { x_carriage = 1 }  # or over placed bodies: bodies = ["x_carriage", "motor_x"],
                            # or over what an axis moves: moving = "x" (one of the three)
max_g = 400

[[interface]]               # holes in a that point into b must line up, sized for M3
a = "syringe_clamp"
b = "x_carriage"
fastener = "M3"

[[heat]]                    # every other body within radius_mm of the source must be rated for temp_c
source = "hot_plate"        # a body, or at = [x, y, z]
temp_c = 250
radius_mm = 15
margin_c = 20               # optional headroom; clear = ["pcb"] also keeps those bodies out of the zone

[[deflection]]              # a body as a beam: the most it may sag (Euler-Bernoulli, Roark's Table 8.1)
body = "gantry_beam"        # a part module, or a bought part declared geometry = "exact"
support = "simple"          # simple, fixed or cantilever
span_mm = 400               # default: its length
load_g = 350                # or load_n, or load_moving = "y" (the mass axis y moves); self_weight = true adds its own
max_um = 50                 # also at, direction (default "-z"), axis, solid = true (a solid bar of an extrusion's size)

[[axis]]                    # the design must declare this axis in AXES, and it must do this
name = "x"                  # only name is required; a sub-assembly's axis is "gantry/x"
moves = ["block", "tool"]   # at least these; only = true: and no others
direction = [1, 0, 0]       # along this line, within tol_deg (default 1)
travel_min_mm = 80          # also travel_max_mm, work_min_mm, tool = "tool" (the body that carries the tool point)

[bodies]                    # exactly this many bodies, and/or exactly these
count = 6
names = ["rail", "block", "stop_left", "stop_right", "tool", "carriage_plate"]

[shop]                      # this design goes to a shop: the shop part rules run; every key is optional
bom = { wheel = 2 }         # how many of each BOM line
orderable = true            # every bought line has a vendor and a part number
mass = "known"              # every line has a mass with its source
files = ["chassis.dxf", "wheel.3mf"]    # files `cad shop` must make
```

An `[[interface]]` judges the holes of `a` whose axis lands on `b` (on its
material or in one of its holes), not every round face: a cutout over a window in
`b` is no mounting hole. A counterbore is part of its hole (the narrowest bore is
the size), a teardrop's point, a D's flat or a slit leaves a bore a hole, a slot
passes when the other body's hole sits on its centre line, and fillets are not
holes. A fastener's clearance hole is anything from ISO 273's fine to coarse
series (M3: 3.2 to 3.6 mm). `near_mm = 15` also asks for a hole within 15 mm of `b`.

Add `[[heat]]` when anything in the brief is hot, `[[deflection]]` for a beam that
carries a load, `[[axis]]` and `[bodies]` when the brief names axes or a number of
bodies, `[shop]` when files go to a shop. `[[heat]]` is a distance and a rating, not a
thermal model: every body inside the zone, or touching the source, is held to `temp_c`.
`[[deflection]]` is a formula, not finite elements, and says UNCHECKED where it would not
hold. They read what a body is made of (a part module's `MATERIAL`, or a bought part's
`mass_g`, `max_temp_c` and `geometry`, which the library fills in); a number nobody
states is unknown, and makes the row UNCHECKED. A `pose` has to be in `POSES` of
assembly.py.

`tests/fixtures/*/spec.toml` are real examples; `mini_machine` uses every section.

## Two rules that carry the run

1. **No bought part modelled from memory.** Look in the library first: `bin/cad lib ls`
   and `lib info <entry>` (rails, carriages, extrusions, NEMA motors, fasteners, each
   with its source), then `bin/cad lib use <slug> <entry> [KEY=VALUE ...]` copies it
   into `bought/` with its mass and hash (don't edit the copy: its hash is pinned, and
   `lib use --replace` writes it again), and `bought_solid(SLUG, "<name>")` (from
   `cad_agent.state`) in assembly.py loads it. Otherwise register a vendor STEP with
   `bin/cad bought add-step <slug> <name> <file> --source <url>`, or a datasheet
   envelope with `bought add-measured ... --source "<page>"`. A remembered bolt
   circle is how an assembly passes every check and still does not fit.
2. **`cad` output is ground truth.** Quote it. Never reason about whether a part
   fits; measure it.

Memory is for judgement (which process suits a part), never for dimensions, prices,
masses, temperature ratings or what a vendor stocks. Use `bin/cad tables` for hole
sizes, tap drills, insert bores, extrusion profiles and `tables materials` (density,
stiffness and service temperature, each with its source).

## Defaults when the brief is silent

| Unknown | Default |
|---|---|
| Process | FDM for brackets, CNC for anything hot or load-bearing, laser cut for panels |
| Material | PETG printed, 6061 aluminium machined, 3 mm acrylic panels |
| Fastener | M3 unless load says otherwise |
| Clearance | 0.2 mm sliding, 0 mm bolted joints, 20 mm around anything over 100 C |
| Material in a hot zone | steel or stainless: `tables materials` rates aluminium 170 C, brass 120 C, copper 200 C, printed plastics lower |

## Writing a part module

`parts/<name>.py` exposes a docstring (first line: what it is; body: why it is
shaped that way, and where any bought-part number came from), `PARAMS` (every
dimension, named), `MATERIAL` (a key of `bin/cad tables materials`: it gives the
mass, heat and deflection rules their numbers), `PROCESS`, `MIN_FEATURE_MM`, and
`build(**params)` returning one solid. `EXPECT_FEATURES` states the cutout count
for flat parts (0 for a plain plate). `CUTLIST` is optional. The process gates
read the geometry: a `laser_cut` part's round holes are 1.0 mm or more and its
slots and gaps at least the 0.15 mm kerf, a `cnc` part's holes and slots 1.0 mm or
more (each `cad check` row names its limit), and a printed part has no hole floor.

`assembly.py` exposes `parts()` returning `{name: positioned solid}`, plus
`CLEARANCE` and `ALLOW_CONTACT`. Contact is never allowed implicitly. `AXES`
declares what moves, so the sweep gate can check the whole travel. `POSES =
{"park": {"x": -150}}` names a position of the machine (axis positions in mm, inside
travel) for the spec entries that say `pose = "park"`. A body that is neither a part
module nor a bought part is stock, with no mass and no rating, and `mirror()`, `scale()`
and a boolean turn a bought solid into one (a mirrored motor named `motor_right`):
build the second one again, or rotate it.

## A machine of several projects

When a part of the machine is a design of its own (a gantry, a head, a dock), make it a
project with its parts, its spec and its own `cad verify`, and link it from the machine's
assembly.py. A bracket or an enclosure stays one project: a machine's check costs about
twice what the same bodies cost in one.

```python
# in the machine's assembly.py
SUBASSEMBLIES = {"gantry": {"project": "gantry", "at": [0, 0, 120], "turn": [0, 0, 90]}}
AXES = {"z": {"moves": ("gantry/*",), "direction": (0, 0, 1), "travel": (0, 50),
              "work": (0, 40)}}                       # "gantry/*" is every body of that instance
POSES = {"park": {"gantry/x": -150}}
```

- Bodies are `gantry/x_carriage`, axes `gantry/x`, poses `gantry/park`; `at` (mm) and `turn`
  (degrees, Rx.Ry.Rz) move the child's whole frame. A body of the machine's own never has a "/".
- Write each `project` as a plain string: verify reads the tree without running it, and a
  name it cannot read leaves the verdict UNCHECKED.
- `cad check machine` runs every gate of every project below it (their rows read
  `<project>:fit/clearance`), and `cad verify machine` rebuilds the whole tree in one fresh
  process. The machine is not done until each child has a spec.toml and approved renders
  (`cad approve gantry` is the human's call).
- A cycle, more than 8 levels, a missing project, a bad entry or a "/" in your own body's
  name is a FAIL row `subassembly/<kind>`, all listed at once.
- A child's parts are cut and drawn from the child (`cad shop gantry` once it is done itself).
  The machine's `cad shop` makes files for its own parts, and its BOM nests the child's.

## When a rule says UNCHECKED

A rule that lacks a number says UNCHECKED and names it. Give it the number; don't loosen the spec.

| Rule | Needs | UNCHECKED when |
|---|---|---|
| `[[heat]]` | a rating for each body in the zone | no `MATERIAL`, or one `tables materials` does not list; a stock body (assembly.py builds it); a bought part with no `max_temp_c` and `max_temp_source` |
| `[[mass]]` `bodies`/`moving` | a mass for each body | a stock body; a bought part with no `mass_g` and `mass_source`. Over `max_g` already is a FAIL |
| `com` (always on) | the same masses | N/A until a bought part declares a mass; from then on UNCHECKED while any body has none (FAIL when the centre of mass is outside the footprint, at home or at an end of an axis's travel) |
| `[[deflection]]` | exact geometry, a `MATERIAL` with a modulus, the load's mass | stock or envelope geometry; a solid box of a 2020, 2040 or 4040's size (use the library's profile, or `solid = true` for a real bar); span/depth under 10 (20 for fixed ends); a section that varies past the limit |
| `[[axis]]`, `[bodies]`, `pose` | the axis, bodies and pose to exist | a body that is not there; a pose not in POSES or outside travel; `pose` on a section that ignores it |
| `[shop]` | vendor, part number, mass | `orderable`: a bought line without a vendor or part number; `mass = "known"`: a line without a mass |
| bought parts | a source, and a hash for a library copy | a part marked unverified (the GT2 idler and the FreeCAD-library STEPs, until `cad bought verify`); a catalog that moved on since the copy |

## Files for a shop

```
bin/cad export <slug> <part> --format step|stl|3mf|dxf   # one file into out/; it writes what you ask for and judges none of it
bin/cad bom <slug>                       # out/bom.csv and bom.json: a line per distinct thing, with kind, material, process, vendor, PN, mass
bin/cad shop <slug>                      # out/shop/: STEP of every made part, DXF (laser_cut), 3MF and STL (fdm), drawings, bom, manifest.json
bin/cad shop <slug> --draft              # the same for a design that is not done, NOT VERIFIED inside every file
bin/cad shop <slug> --check              # regenerate and compare with out/shop/ by sha256
bin/cad drawing <slug> <part>            # DXF, SVG and PDF of a cnc or laser_cut plate, with the sizes and the holes
```

- `shop` writes nothing and exits 2 unless `cad done` holds; a FAIL or UNCHECKED row stops it
  too. A `[shop]` table in the spec turns on the part rules: a laser part must be a
  through-cut that its DXF reads back to, a printed part's 3MF must be watertight.
- `drawing` draws a prism along its thinnest axis (outline, round holes, slots, windows through)
  and says why when a part is anything else. Its sheet says NOT VERIFIED until `cad done`.
- Exit codes are the usual (0 ok, 1 FAIL, 2 UNCHECKED, 3 bad arguments, 4 crash). `lib`: 1 for
  a file that is not the one a pin names, 2 when the network does not answer, 3 for an unknown
  entry or a licence that bars `fetch`. `bom` never exits 2. `shop` and `drawing`: 2 for a design
  that is not done (a draft is written and still exits 2) or a row UNCHECKED, 1 for a FAIL; `drawing`
  exits 3 for a part that is not cnc or laser_cut, and 2 for one that is not a plate.

## Renders and approval

Look at every render you make (Read the PNG). The visual gate compares renders
with approved baselines, and approving one is **the human's call**. Show the
render and the diff, and let them run `bin/cad approve` (or click Approve in
the workbench). Don't approve your own work.

## The workbench and hand moves

`bin/cad serve` runs the workbench, a live 3D page for the human (the app's
Browser pane opens it). It rebuilds within seconds of your edits, so they can
watch. When they drag a part there, it lands in `placements.toml`, a rigid move
on top of `assembly.py` that every gate and `cad verify` see.

- `git diff placements.toml` shows what they moved. Treat a move as a request:
  fold it into `assembly.py` (change the `Pos`/`Rot`, or the parameter behind
  it), then delete the entry with `bin/cad place <slug> <body> --reset`.
- To try a position yourself, run `bin/cad place <slug> <body> --by=DX,DY,DZ` (or
  `--turn=RX,RY,RZ`). It reports what the body now hits, and exits 1 on a
  fit failure. Write `--by=-5,0,0` when the first value is negative.
- A settled design has no placements.toml. The code is the source of truth.
- They can also change a part's PARAMS from the page (`cad set`, which you can
  run too: `bin/cad set <slug> <part> thickness=6`). That edits the part file
  itself, so it shows in `git diff` like any edit. Keep PARAMS values plain
  literals where you can, so they stay editable there.

## Finish

1. `bin/cad check <slug>`: fix every FAIL. Explain every UNCHECKED you can't close.
2. Commit the design (parts, assembly, spec, bought, baselines).
3. `bin/cad verify <slug>`, then `bin/cad done <slug>`. A machine's children need
   their own spec.toml and approved renders first.
4. If the brief wants files for a shop: `bin/cad shop <slug>`, then `--check` shows
   out/shop/ is what a fresh run writes.
5. For a second opinion on what no rule covers, ask the `cad-reviewer` agent.
   To share the result, `bin/cad page <slug>` writes a review page; publish its
   folder as a private artifact (index.html plus the files next to it).
6. Report: the verdict line from `cad done`, measured numbers quoted from the
   output, the assumptions you made, and what the human still has to do.
