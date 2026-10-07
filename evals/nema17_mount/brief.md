# nema17_mount: a NEMA 17 motor beside a 2040 rail, held by one plate

Design the bracket for a NEMA 17 stepper beside a short piece of 2040 extrusion: one flat
aluminium plate that lies on top of the rail and carries the motor underneath it, shaft up
through the plate. Everything the grader checks is listed here, in numbers.

## What exists

Your project `nema17_mount` already holds one given file (do not `cad init` it):

- `bought/nema17_motor.step` (+ `nema17_motor.json`, its source). The STEP origin is the middle
  of the mounting face, the shaft points +z and the body sits behind the face (z -40 to 0).
  The face has four tapped M3 holes (2.5 mm) on a 31 mm square, a 22.0 mm pilot boss 2 mm high,
  and a 5 mm shaft sticking 24 mm out of the face. Bounding box 42.3 x 42.3 x 64 mm.

Given files are laid again over your project before scoring, so editing them gains nothing.

Where the numbers come from: the 31 mm pattern, 22 mm pilot and 5 mm shaft are NEMA ICS 16
frame 17; 42.3 mm square, 40 mm body and 24 mm shaft are the common 17HS4401 outline (datasheets
differ by a few mm on the shaft). The STEP is modelled from those figures, not a vendor file.
The rail is `cad tables extrusions`' 2040: 20 x 40 mm.

## The assembly: exact body names

`assembly.py` returns these bodies, with these names, in one frame (x across the rail, y along
it, z up; z = 0 is the rail's top face):

| body | what | placed |
|---|---|---|
| `extrusion` | 60 mm of 2040 with its 40 mm side vertical: `extrusion_blank("2040", 60, axis="y")` from `cad_agent.parts`, 20 x 60 x 40 mm | bounding-box center (0, 0, -20): top face on z = 0 |
| `nema17_motor` | the given part (`bought_solid` in `cad_agent.state`), moved by translation only | STEP origin at (35, 0, 0): bounding-box center (35, 0, -8), mounting face on z = 0, shaft up |
| `bracket` | yours: part module `parts/bracket.py`, aluminium (`MATERIAL = "aluminium"`, a `PROCESS` of your choice) | wherever your design puts it |

## What is checked

1. **Pinned bodies.** `nema17_motor` is 42.3 x 42.3 x 64 mm (bounding box, +-0.1) with its
   bounding-box center at (35, 0, -8) within 0.1 mm. `extrusion` is 20 x 60 x 40 mm (+-0.1) with
   its center at (0, 0, -20) within 0.1 mm.
2. **The bracket is a real plate.** Its bounding box is at least 62 x 42.3 x 4 mm (x, y, z): it
   covers the whole motor face and is stiff enough.
3. **It lies on the rail.** The closest distance between `bracket` and `extrusion` is at most
   0.05 mm. Touching counts; overlapping fails.
4. **It sits flat on the motor.** The closest distance between `bracket` and `nema17_motor` is at
   most 0.05 mm, again touching but not overlapping. The motor's pilot has to go into a bore.
5. **M3 holes.** Each of the motor's four tapped M3 holes has a hole in the bracket on the same
   axis, within 0.1 mm, and the pair suits an M3 screw: the bracket's holes are M3 clearance holes
   (3.2 to 3.6 mm, ISO 273 fine to coarse; `cad tables holes` has the 3.4 mm medium size).
6. **Mass.** `bracket` weighs at most 32 g, computed from its `MATERIAL`.
7. **Envelope.** Rail, motor and bracket together fit in 72 x 60 x 64 mm (x, y, z).

The usual `cad` gates apply on top of these: no two bodies overlap, and every part passes the
part rules for its `PROCESS` (`cad rules`; a flat part declares `EXPECT_FEATURES`).

## Working

Write your own `spec.toml` first, with these requirements as `[[size]]`, `[[position]]`,
`[[clearance]]` (`max_mm` for "touches"), `[[interface]]`, `[[mass]]` and `[[envelope]]` entries
(`cad_agent/spec.py` has the format), then `parts/bracket.py` and `assembly.py`, then `cad check
nema17_mount`. Finish with a commit, `cad verify nema17_mount` and `cad done nema17_mount`.

## How it is graded

The grader copies your project, puts the given files and its own `spec.toml` (the list above and
nothing else) over the copy, and runs `cad verify` on it in a fresh process. Your own `spec.toml`
is not read. The score is the share of rows that pass; PASS needs every one. Rows that wait on a
person approving a render (`drift/`, `extent/`) are not counted.
