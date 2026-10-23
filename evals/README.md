# evals: design tasks scored by the verifier

Each task is a small brief with a hidden `spec.toml`. An agent designs through the `cad` CLI and
`cad verify` scores what it leaves, so "better" is a number: run the set before and after a change
to cad-agent (a rule, the skill, a hook, the CLI) and compare. There are 12 tasks: phase 1 and phase
2, and two that step 6 added for its new rules (`dock_material`, `beam_deflection`). No real agent has
run them yet: the command is under "Suggested real run" below.

## Layout

```
evals/<task>/
  brief.md     what the agent gets: every requirement the hidden spec checks, in words and
               numbers; the exact body names assembly.py must use; which given files exist; and
               that given files are laid again before scoring, so editing them gains nothing
  spec.toml    the hidden spec, the grader. The agent writes its own and never sees this one
  given/       files laid into the agent's project at the start and again before grading, in the
               project's own layout: given/bought/x.step -> projects/<task>/bought/x.step
  reference/   a complete design (parts/, assembly.py) that scores 100%: proof the task can be
               solved, and what the tests break to check each rule is really graded. A task whose
               answer is stock, a beam, has a library part instead of a part module: what `cad lib
               use` copied into reference/bought/
  source/      phase 2 tasks and step 6's: the script that makes the given STEPs, with the source of
               every number (and what a rule of step 6 reads from a given part's note: a mass, a
               rating). Never laid into the agent's project
evals/make_given.py   the same for the phase 1 tasks (modelled in build123d)
evals/results/        what `cad eval run` scored, one JSON per run (not in git)
```

Given parts are bought parts (a STEP with a sidecar naming its source), not part modules. A part
module would bring the part gates' rows with it, and could fail them; a bought part adds one
provenance row, which passes.

| task | what it checks |
|---|---|
| `nema17_mount` | a plate on a 2040 rail carrying a NEMA 17: the M3 pattern on the motor's 31 mm square, touching rail and motor, mass, envelope, the motor pinned |
| `syringe_clamp` | a clamp that holds a 10 mL barrel 0.05 to 0.35 mm off, bolted to a plate with an off-centre syringe: `max_mm` as "grips", an M3 interface, mass |
| `galvo_mount` | a mount that stands on the bench and holds a galvo head, outside the laser cone: a `[[keepout]]`, an M4 interface, mass |
| `mgn12h_carriage` | a plate on an MGN12H block that carries a tool flange between two end stops: an M3 pattern to the block and one to the tool, a size range, 42 mm to each stop at home, mass, exactly six bodies (`[bodies]`), and `AXES` declared (`[[axis]]`: `x` moves the block, plate and tool, 80 mm of travel) |
| `hotplate_standoffs` | four standoffs holding a 250 C plate 20 mm over a base: each touching both (`max_mm`), an M3 bore over the plate's tapped holes, the 20 mm air gap, exactly six bodies, and the standoffs' material against a 250 C `[[heat]]` zone (only steel, stainless and polyimide pass) |
| `pinned_carrier` | a block that locates on two dowel pins (0.1 mm to spare at most, `max_mm`), seats on the base and clears a screw head by 0.5 mm: coaxial holes and a relief pocket, no fastener, exactly five bodies |
| `laser_panel` | a 3 mm laser-cut panel on a frame, with a button hole and an OLED window each 0.10 to 0.40 mm off its part (`min_mm` with `max_mm`), M3 mounting, an envelope held from both sides |
| `pcb_enclosure` | a base and a lid for an Arduino UNO with its USB plug in: standoffs on the board's own holes (read from the board, axes only), a window the plug clears by 1 mm, a floor on each size |
| `idler_bracket` | a bracket on a 2040 end holding a GT2 idler's M5 shaft: M5 mounting holes, shaft holes judged by the shaft's gap (0.1 to 0.5 mm) since no fastener size fits its 5.0 bore, 0.5 mm to the idler, exactly four bodies |
| `endstop_bracket` | a bracket that holds a microswitch where a carriage flag presses its lever: M2 holes read from the switch, the flag within 0.5 mm, the switch's size as a range so it can turn a quarter turn |
| `dock_material` | a rail bolted 2 to 4 mm off a 250 C hot plate on a steel base plate: M4 bolts on the base's tapped holes (judged both ways, so no base hole is left uncovered under it), and the point of the task, a 15 mm `[[heat]]` zone: the dock's `MATERIAL` is rated by `cad tables materials`, and only steel, stainless and polyimide pass. The base plate is in the zone too and passes on the rating its own note declares; exactly three bodies |
| `beam_deflection` | a beam on two steel blocks 600 mm apart, with 2.5 kg at midspan and its own weight: a `[[deflection]]` of at most 50 um, and at most 600 g. The beam is stock (no process's working volume takes a 640 mm part module), so it comes from the library: the 2040 on its 40 mm side is the one that passes (37.7 um, 499 g); a 2020 or a flat 2040 sags too much, a 4040 weighs too much, and the box of a 2040's outer size is UNCHECKED |

## Commands

```
cad eval ls                                   tasks: the brief's first line and what is given
cad eval brief <task>                         the brief, then the given files
cad eval score <task> <design_dir> [--keep] [--all]
cad eval run --agent CMD [task ...] [--timeout S] [--keep] [--out FILE]
```

The tasks folder is `--evals DIR`, else `CAD_EVALS`, else `evals/` next to the package. `--json`
works on all of them, and the exit code is the verdict: 0 PASS, 1 FAIL, 2 UNCHECKED, 3 usage.

**`score`** copies `<design_dir>` (a project folder: `parts/`, `assembly.py`, ...) to a scratch
`projects/<task>`, drops its outputs and approved renders (`checks.json`, `verify.json`, `out/`,
`.cad/`, `baseline/`), lays `given/` over it and the hidden `spec.toml` over the agent's, and runs
`cad verify` on the copy in a fresh process (through the warm worker like any call, with
`PYTHONPATH` on this package so the grader is the code that is running). `--keep` leaves the
scratch folder and prints it; `--all` shows passing rows too.

- Every row counts except the ones that wait on a person approving a render: rules starting
  `drift/`, `extent/` or `visual/` (the edit hook skips the same three). N/A is not held against a
  design. A part that failed to build counts as a failed row.
- Score = passed rows / graded rows. The verdict is PASS only if no graded row is FAIL or
  UNCHECKED, no part failed to build, and verify reports a fresh process and a design that did not
  change while it ran. FAIL outranks UNCHECKED, as in `cad verify`. A verify that crashes or times
  out is a FAIL with the reason as its one row.
- `--json` gives `task`, `verdict`, `score`, `graded`, `passed`, `skipped`, `na`, `notes`, `rows`,
  `seconds` and `verify_seconds`.

**`run`** does that for an agent. For each task it makes a temp git repo: `projects/<task>/` with
the given files, `BRIEF.md` at the root, one commit. It runs `--agent CMD` through the shell with
the repo root as the working directory and `CAD_PROJECTS=<root>/projects`, replacing `{brief}`
(path of BRIEF.md), `{dir}` (the project folder), `{task}`, `{root}` and `{plugin}` with
shell-quoted values, then scores the project folder. A table prints and the results go to
`evals/results/<UTC stamp>.json` (or `--out`): per task the verdict, score, the failing rows, how
long the agent took, and the tail of its output. The agent gets `--timeout` seconds (default 1800)
per task and is killed with its process group after that; what it left is still scored. `--keep`
keeps each task's repo and agent log, and the plugin copy.

**`{plugin}`** is the repo as a plugin, minus what grades: a copy without `evals/` (the hidden specs
and the references), `.git` (every commit still has them), `.venv`, caches and `.claude/worktrees`
(other agents' checkouts, each with its own `evals/`). It is made once per run, only when the
command uses `{plugin}`, and removed at the end. The plugin's first-run hook installs the CAD
kernel for the copy's path, so that takes its few minutes once per run. The agent's environment has
no `CAD_EVALS`.

## What a score does not prove

- It reads the geometry `assembly.py` produced, not how. An assembly could edit a given part's
  solid; the pins hold its bounding box and position, not its holes.
- `[[interface]]` judges the holes of `a` whose axis lands on `b`, on its material or in one of its
  holes: a design that leaves a given hole uncovered is judged on the rest. A hole is a bore that
  turns 270 degrees or more (a teardrop, a D-bore and a slit bore count; a counterbore is part of
  it, and it is sized by its narrowest bore) and a slot is judged by its centre line; fillets and a
  notch open to an edge are not holes, so nothing judges them. `near_mm` is an explicit extra:
  only holes that close to `b`.
- `max_mm` on a clearance is the closest approach: a looser bore with the barrel resting on one side
  can pass "grips", and a part tilted onto one edge passes "touches". `[[shaft_fit]]` judges a round
  part in its bore by the two diameters and its axis, and `syringe_clamp` grades its bore with it. `[[mass]]` uses the `MATERIAL` the part declares.
- The `kerf` row of a `laser_cut` part reads slots and the air between flat walls that face each
  other; a curved gap other than a slot's ends (a ring groove) is not read. `min hole` reads round
  holes, and on a `cnc` part slots too. A printed part has no hole floor.
- `[[heat]]` is a zone and not a thermal model: every body within the radius is held to the zone's
  temperature as if it touched the source, so an air gap or an insulator inside the radius buys
  nothing, and the rating is the table's (a plastic's is its heat deflection temperature, where it
  starts to give, not a life rating). A body with no rating is UNCHECKED, and so is a bought part
  that declares none, which is why `dock_material`'s given base plate declares one.
- `[[deflection]]` is a formula (Euler-Bernoulli, with ideal supports) on the beam's own sections:
  no shear, torsion, buckling or give at the supports. It says UNCHECKED rather than guess for a
  section it cannot read, so a solid box of a 2020, 2040 or 4040's outer size is no beam it judges.
- Nothing here judges assembly order, tool access or cable routing; that is the reviewer's job.
- The agent can read whatever folder it is pointed at. The hidden specs and the references are in
  this repo, which is also the plugin, so a real run says `--plugin-dir {plugin}` (the copy above).
  Pointing it at the repo itself puts them one `ls` away. The copy still has the docs: PLAN_V2.md and
  ui/HANDOFF.md name the tasks and say what the grader does not check.

## Adding a task

1. Decide what it tests and what a careless design gets wrong.
2. Write the given parts as bought parts: a script in `evals/<task>/source/` (or a model in
   `make_given.py`, or `cad bought add-step`) with a source line that says what the numbers are and
   are not. Write its STEPs with `cad_agent.export.write_step`, not build123d's `export_step`: the
   second puts the clock and OCCT's occurrence counter in the file, so a rerun changes it
   (`tests/test_export.py` fails on a raw `export_step`).
3. Write the reference in a scratch project named after the task (its `assembly.py` finds its parts
   by that name, `SLUG = "<task>"`) until `cad check` is clean, then copy `parts/` and `assembly.py`
   into `reference/` (and `bought/`, if the answer is a library part `cad lib use` copied in). The edit and stop hooks skip everything under `evals/`, so nothing checks a
   reference where it lies and nothing is written into it. Then the hidden `spec.toml`: pin every
   given body with `[[size]]` and `[[position]]`, and write "touches" and "grips" as `max_mm`.
4. Write `brief.md`: every number, every body name, every given file, the rule that given files are
   laid again. `tests/test_eval.py` fails if the brief leaves out a body, a given file or a number
   the spec holds a design to (it reads numbers, so 13 and 13.0 are one; a size pinned to 0.1 mm is
   stated as its nominal `a x b x c`, and a range or a floor as its limits), `[[heat]]`,
   `[[deflection]]`, `[bodies]` and `[[axis]]` included. A given body inside a heat zone declares its
   rating in its note (`max_temp_c` with `max_temp_source`) and one the centre-of-mass rule must weigh
   its `mass_g` with `mass_source`: the task's source script adds them to the note.
5. Add the task to `TASKS`, `SPEC_RULES` and `BROKEN` in `tests/test_eval.py`: a one-line edit to
   the reference that must fail on one named rule. When the edit breaks what follows from it too
   (a pin that no longer fits its hole also overlaps the block), `BROKEN` names all the rules.
6. `cad eval score <task> evals/<task>/reference` says PASS 100.0%.

## Suggested real run (not run yet)

```
bin/cad eval run --agent 'claude -p "$(cat {brief})" --plugin-dir {plugin} --permission-mode acceptEdits'
```

It spends plan usage: each task is a whole design session. Try `bin/cad eval run ... nema17_mount
--timeout 900` first. Compare the mean score between runs, and `rows` in the results file for what
moved. Keep `--plugin-dir {plugin}`: see the note above about what the agent can read.

## Known gaps

What the grader cannot say yet, and how the tasks go round it. Each is a rule or a `spec.toml` kind
to add; none was needed to write the twelve tasks.

Closed by step 6, and no longer gaps: `[[axis]]` can require that `AXES` is declared (`mgn12h_carriage`
does), `[bodies]` holds an exact body count and names (the four tasks whose briefs say "exactly" do, and
the two new ones), `[[heat]]` is a heat rule (`hotplate_standoffs` and `dock_material`), and
`cad export --format dxf` makes the DXF of a laser part.

- ~~No hole-count option and no shaft-fit option~~: `[[holes]]` and `[[shaft_fit]]` exist now.
  `pinned_carrier` counts its two pin holes and `hotplate_standoffs` each standoff's bore, through
  (`through = true`: a hole drilled blind passed every other rule); `syringe_clamp`'s bore is a
  `[[shaft_fit]]` on the barrel (a loose bore pushed to one side passed the closest approach).
  `tests/test_eval.py` GAPS holds each of those designs. `idler_bracket` keeps the closest-approach
  range (0.1 to 0.5 mm) for its shaft holes: their axes are held within 0.1 mm of the shaft's, which
  bounds the hole already. A hole left out is still caught only when the given body is `a`, as in
  `pcb_enclosure` and `endstop_bracket`, or where `[[holes]]` counts them.
- A clearance `max_mm` bounds only the closest approach (said above; documented, and `[[shaft_fit]]`
  covers a round part). A flat face held flat on another ("seats flat") has no such rule, and there is
  no clearance to a sub-feature: "the pocket clears the screw head" is a distance between two bodies.
- No task spans more than one project: a sub-assembly is a sibling folder and `cad eval score` lays
  one design. `tests/fixtures/mini_machine` tests a machine of two projects; scoring one is step 8.
