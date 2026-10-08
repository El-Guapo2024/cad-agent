---
name: cad
description: Design mechanical parts and assemblies with the cad-agent CLI (build123d). Write parametric part modules, an assembly and a spec.toml, run the gates, look at renders, and finish only when `cad verify` then `cad done` pass. Use for any 3D mechanical design task in this repo, or when the user says "design a part", "bracket", "mount", "enclosure", "gantry", or asks to check, verify or render a cad project.
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

## The boundary

**You specify. The kernel computes. The verifier decides. The human fabricates.**

- Never state a dimension a command could measure. Quote `cad` output.
- Never draw a diagram. Renders come from the same geometry the gates judged.
- Never decide a design is done. `cad done` decides.

## The loop

```
bin/cad init <slug> --brief "..."             # new project
# write spec.toml first: what the design must do (below)
# write parts/<name>.py, then assembly.py
bin/cad check <slug> --part <name>            # fast loop, part rules only (~1 s)
bin/cad build <slug> <name> --set t=5         # sweep a value without editing the file
bin/cad render <slug> [<name>] --view iso     # prints a PNG path: Read it and look
bin/cad measure <slug> <a> <b> --posed        # the raw fit query between placed bodies
bin/cad check <slug>                          # every gate, including the spec
git commit                                    # the verifier only counts committed work
bin/cad verify <slug>                         # fresh rebuild; verdict tied to the commit
bin/cad done <slug>                           # exit 0 only if that verdict still stands
```

A hook runs `cad check` after every edit to a part, assembly or spec, and hands
back what fails. A stop hook will not let you finish over a changed project
that `cad done` rejects. Fix what they name, or say plainly that the design is
not done and why.

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

[[mass]]                    # a budget over part modules
parts = { x_carriage = 1 }
max_g = 400

[[interface]]               # holes in a that point into b must line up, sized for M3
a = "syringe_clamp"
b = "x_carriage"
fastener = "M3"
```

An `[[interface]]` judges the holes of `a` whose axis lands on `b` (on its
material or in one of its holes), not every round face: a cutout over a window in
`b` is no mounting hole. A counterbore is part of its hole (the narrowest bore is
the size), a teardrop's point, a D's flat or a slit leaves a bore a hole, a slot
passes when the other body's hole sits on its centre line, and fillets are not
holes. A fastener's clearance hole is anything from ISO 273's fine to coarse
series (M3: 3.2 to 3.6 mm). `near_mm = 15` also asks for a hole within 15 mm of `b`.

`tests/fixtures/*/spec.toml` are real examples.

## Two rules that carry the run

1. **No bought part modelled from memory.** Register a vendor STEP with
   `bin/cad bought add-step <slug> <name> <file> --source <url>`, or a datasheet
   envelope with `bought add-measured ... --source "<page>"`. A remembered bolt
   circle is how an assembly passes every check and still does not fit.
2. **`cad` output is ground truth.** Quote it. Never reason about whether a part
   fits; measure it.

Memory is for judgement (which process suits a part, that a printed bracket
creeps near a hot plate), never for dimensions, prices or what a vendor stocks.
Use `bin/cad tables` for hole sizes, tap drills, insert bores and extrusion
profiles.

## Defaults when the brief is silent

| Unknown | Default |
|---|---|
| Process | FDM for brackets, CNC for anything hot or load-bearing, laser cut for panels |
| Material | PETG printed, 6061 aluminium machined, 3 mm acrylic panels |
| Fastener | M3 unless load says otherwise |
| Clearance | 0.2 mm sliding, 0 mm bolted joints, 20 mm around anything over 100 C |

## Writing a part module

`parts/<name>.py` exposes a docstring (first line: what it is; body: why it is
shaped that way, and where any bought-part number came from), `PARAMS` (every
dimension, named), `MATERIAL`, `PROCESS`, `MIN_FEATURE_MM`, and
`build(**params)` returning one solid. `EXPECT_FEATURES` states the cutout count
for flat parts (0 for a plain plate). `CUTLIST` is optional. The process gates
read the geometry: a `laser_cut` part's round holes are 1.0 mm or more and its
slots and gaps at least the 0.15 mm kerf, a `cnc` part's holes and slots 1.0 mm or
more (each `cad check` row names its limit), and a printed part has no hole floor.

`assembly.py` exposes `parts()` returning `{name: positioned solid}`, plus
`CLEARANCE` and `ALLOW_CONTACT`. Contact is never allowed implicitly. `AXES`
declares what moves, so the sweep gate can check the whole travel.

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
3. `bin/cad verify <slug>`, then `bin/cad done <slug>`.
4. For a second opinion on what no rule covers, ask the `cad-reviewer` agent.
   To share the result, `bin/cad page <slug>` writes a review page; publish its
   folder as a private artifact (index.html plus the files next to it).
5. Report: the verdict line from `cad done`, measured numbers quoted from the
   output, the assumptions you made, and what the human still has to do.
