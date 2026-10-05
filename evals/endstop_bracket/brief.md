# endstop_bracket: a bracket that holds an endstop switch where the carriage's flag reaches its lever

A 2040 extrusion stands upright, and a carriage (not modelled) rides down its +x face. At
the bottom of its travel the carriage's flag comes down onto the lever of a microswitch
and presses it. Design the bracket that holds the switch there, on the extrusion.

Your project is called `endstop_bracket`, and it must keep that name: assembly.py and the
parts refer to it as `SLUG = "endstop_bracket"`, and the grader copies the project to a
folder with that name.

## Given

Three bought bodies are already in `bought/`. Each has a `.json` next to it that says where
its numbers came from. All are laid over your project again before grading, so editing them
gains nothing.

| file | what | bounding box, mm |
|---|---|---|
| `bought/extrusion_2040.step` | a 2040 profile, 200 mm long, as its outer envelope (no slots), centred on its own origin with the length along z | 20 x 40 x 200 |
| `bought/carriage_flag.step` | the carriage's flag, a plain block centred on its own origin | 6 x 12 x 14 |
| `bought/omron_ss5gl.step` | an Omron SS-5GL microswitch with a hinge lever, drawn in the frame below | 19.8 x 6.4 x 15.2 |

The switch's frame is the datasheet's side view. The origin is the midpoint of the two
mounting holes, x runs along the 19.8 mm body, z is up toward the lever, and y runs through
the 6.4 mm thickness. In that frame:

- The two mounting holes are 2.35 mm in diameter, 9.5 mm apart, with their axes along y
  at z = 0 and x = -4.75 and +4.75. The switch screws to a panel through them. The datasheet
  gives the panel holes as 2.4 mm or M2.3 screws.
- The body spans x -9.85 to 9.95 and y -3.2 to 3.2. Its bottom face is 2.5 mm below the hole
  axes (z = -2.5), and its top is at z = 7.0, or 7.7 over the hinge end.
- The lever is a flat strip 3.6 mm wide and 0.3 mm thick, from x = -6.75 to 9.75 (its tip
  is 14.5 mm from the first hole). It is drawn pressed down to the datasheet's operating
  position, OP = 8.8 +/- 0.8 mm, so its top face is at z = 8.8. A flag touching that face, or
  within 0.5 mm of it, has pushed the lever there. (Free position 13.6 mm at most,
  overtravel 1.2 mm at least.)
- Three solder terminals hang down to z = -6.4.

Where the numbers come from:

- Switch: Omron "SS Subminiature Basic Switch" catalogue B032-E1-14, hinge lever SS-5GL:
  the drawing and table on page 5, the terminals and mounting holes on page 4.
- Extrusion: `cad tables extrusions` (2040 is 20 x 40 mm); the slots are not modelled.
- Flag: a plain block defined by this task.
- `cad bought info endstop_bracket omron_ss5gl` prints the switch's bounding box, and
  `cad_agent.spec.holes(solid)` returns each hole's axis point, direction and diameter, which
  is what the grader uses.

## What assembly.py returns

At least these four bodies, with exactly these names:

| body | what |
|---|---|
| `extrusion` | `Pos(0, 0, 100) * bought_solid(SLUG, "extrusion_2040")`. It stands on z = 0 and runs to z = 200. Its bounding box is centred at (0, 0, 100) with size 20 x 40 x 200. |
| `flag` | `Pos(27.5, 4.0, 47.0) * bought_solid(SLUG, "carriage_flag")`. Its bounding box is centred at (27.5, 4.0, 47.0) with size 6 x 12 x 14: x 24.5 to 30.5, y -2 to 10, z 40 to 54. Its underside, z = 40, is the face that presses the lever. |
| `switch` | `bought_solid(SLUG, "omron_ss5gl")`, placed by you. |
| `bracket` | yours |

`bought_solid` is in `cad_agent.state`.

## What is graded

`cad verify` runs the grader's spec.toml and every normal gate (`cad rules`). Every row
counts except drift, extent and visual, which need a human to approve renders. A
spec.toml of your own is replaced, so it only helps you check your work.

1. **The given bodies stay put.** `extrusion` and `flag` have their bounding-box centres
   within 0.1 mm of the numbers above and their sizes within 0.05 mm.
2. **The switch stays upright.** The flag comes down onto the lever, so the switch is
   mounted lever-side up, in any quarter turn about the vertical axis. Its bounding box is
   then 15.1 to 15.3 mm tall, and 6.3 to 19.9 mm in x and in y (19.8 x 6.4 in plan, either
   way round).
3. **The flag reaches the lever.** The closest approach between `switch` and `flag` is 0 to
   0.5 mm. Touching is fine, overlap is not.
4. **Screws.** Each of the switch's two holes has a hole in the bracket on the same axis,
   within 0.1 mm, sized for M2: the bracket's hole is within 0.15 mm of 1.6 mm (the M2
   tapping drill) or 2.4 mm (M2 clearance), from `cad tables`. The bracket's other holes
   are not judged.
5. **The bracket is on the extrusion.** The closest approach between `bracket` and `extrusion`
   is 0 to 0.5 mm. How it is fastened (slot nuts, a clamp) is yours; the slots are not in
   the model, so no holes are checked there.
6. **The flag only touches the lever.** `bracket` is at least 1.0 mm from `flag`.
7. **Envelope.** The whole assembly fits in 45 x 45 x 200 mm.
8. **No overlaps.** Two bodies may touch but never overlap.
9. **Part gates.** Every part builds, declares a PROCESS, and passes that process's rules
   (FDM needs walls of 0.8 mm or more). A flat part, thinner than a quarter of its longest
   side, must declare `EXPECT_FEATURES` and have at least one cutout, or its web gate cannot
   be settled.

Not graded: the carriage's own body, how the screws look, mass and cost.
