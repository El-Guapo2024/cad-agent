# syringe_clamp: a clamp for a 10 mL syringe on a carriage plate

Design the clamp that holds a 10 mL luer-lock syringe upright against the carriage plate of a
dispensing head: one 3D-printed PETG part that bolts to the plate and holds the barrel. The
syringe sits off to one side of the plate's bolt pattern, so the clamp is not symmetric.
Everything the grader checks is listed here, in numbers.

## What exists

Your project `syringe_clamp` already holds two given parts (do not `cad init` it):

- `bought/carriage_plate.step`: 6 mm aluminium plate, 100 x 80 mm. The STEP origin is the middle
  of the plate's front face: the front face is y = 0, the plate runs from y = 0 to y = 6 behind
  it, x across, z up. Four M3 clearance holes (3.4 mm) go through it on a rectangle 24 mm in x by
  30 mm in z, centered on the origin. Bounding box 100 x 6 x 80 mm.
- `bought/syringe.step`: a 10 mL luer-lock syringe, plunger part way out, modelled solid. The STEP
  origin is on the barrel axis at the underside of the finger flange, +z toward the plunger.
  Barrel 16.0 mm across, 75 mm long (z 0 to -75); finger flange 33 x 14 mm, 3 mm thick (z 0 to
  3); shoulder and luer tip below the barrel down to z = -90; plunger rod and a 22 mm thumb pad up
  to z = 73. Bounding box 33 x 22 x 163 mm.

Each has its source in the `.json` beside it. Given files are laid again over your project
before scoring, so editing them gains nothing.

Where the numbers come from: the plate is the task's own drawing. The syringe follows typical
10 mL luer-lock syringes (16 mm barrel, 33 mm finger flange); makers differ by about 0.5 mm, which
is why the grip below is a range. It is modelled from those figures, not a vendor file.

## The assembly: exact body names

`assembly.py` returns these bodies, with these names, in one frame (the plate's):

| body | what | placed |
|---|---|---|
| `carriage_plate` | the given part (`bought_solid` in `cad_agent.state`) | not moved: bounding-box center (0, 3, 0) |
| `syringe` | the given part, moved by translation only | STEP origin at (10, -16.2, 35): barrel axis at x = 10, y = -16.2, flange underside at z = 35, bounding-box center (10, -16.2, 26.5). The straight barrel runs from z = -40 to z = 35 |
| `syringe_clamp` | yours: part module `parts/syringe_clamp.py`, `MATERIAL = "petg"`, `PROCESS = "fdm"` | wherever your design puts it |

## What is checked

1. **Pinned bodies.** `carriage_plate` is 100 x 6 x 80 mm (bounding box, +-0.1) with its center at
   (0, 3, 0) within 0.1 mm. `syringe` is 33 x 22 x 163 mm (+-0.1) with its center at
   (10, -16.2, 26.5) within 0.1 mm.
2. **It holds the barrel.** The closest distance between `syringe` and `syringe_clamp` is between
   0.05 and 0.35 mm: a printed bore a little over 16.0 mm. Overlapping fails.
3. **It sits on the plate.** The closest distance between `syringe_clamp` and `carriage_plate` is
   at most 0.05 mm. Touching counts; overlapping fails.
4. **M3 bolts.** Every hole in the clamp that points into the plate (its axis meets the plate and
   it lies within 15 mm of it) is on the same axis, within 0.1 mm, as one of the plate's four
   holes, and the pair suits an M3 screw: the plate's side is clearance (3.4 mm), the clamp's is
   a heat-set insert bore (4.0 mm, `cad tables inserts`), a tap drill (2.5) or clearance (3.2 to
   3.6 mm). Screws come from behind the plate.
5. **Mass.** `syringe_clamp` weighs at most 30 g, computed from its `MATERIAL`.
6. **Envelope.** Plate, syringe and clamp together fit in 100 x 40 x 165 mm (x, y, z).

The usual `cad` gates apply on top of these: no two bodies overlap, and every part passes the
part rules for its `PROCESS` (`cad rules`).

## Working

Write your own `spec.toml` first, with these requirements as `[[size]]`, `[[position]]`,
`[[clearance]]` (`min_mm` and `max_mm` for a gap that has to stay in a range), `[[interface]]`,
`[[mass]]` and `[[envelope]]` entries (`cad_agent/spec.py` has the format), then
`parts/syringe_clamp.py` and `assembly.py`, then `cad check syringe_clamp`. Finish with a commit,
`cad verify syringe_clamp` and `cad done syringe_clamp`.

## How it is graded

The grader copies your project, puts the given files and its own `spec.toml` (the list above and
nothing else) over the copy, and runs `cad verify` on it in a fresh process. Your own `spec.toml`
is not read. The score is the share of rows that pass; PASS needs every one. Rows that wait on a
person approving a render (`drift/`, `extent/`) are not counted.
