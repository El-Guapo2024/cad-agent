# galvo_mount: a galvo head over the bench, held outside its own beam

Design the mount that holds a galvo scan head above a work area: one machined aluminium part
that stands on the bench, reaches up to the head, bolts to its side face, and stays out of the
laser beam. Everything the grader checks is listed here, in numbers.

## What exists

Your project `galvo_mount` already holds one given file (do not `cad init` it):

- `bought/galvo_head.step` (+ `galvo_head.json`, its source). The head with its F-theta lens
  barrel. The STEP origin is where the beam leaves the lens, on the head's axis, +z up. The lens
  barrel is 56 mm across and 15 mm long (z 0 to 15) under a 100 x 70 mm body (z 15 to 85). Four
  tapped M4 holes (3.3 mm) on a 40 mm square sit in the +x face (x = 50), centered on y = 0 and
  z = 50 (in the STEP's own frame). Bounding box 100 x 70 x 85 mm.

Given files are laid again over your project before scoring, so editing them gains nothing.

Where the numbers come from: the lens is the one the desk fab line's laser plans on, an F-theta
with a 210 mm focal length, a 150 mm square field and a 30 mm clear aperture (the example in
`cad_agent/spec.py`). The head is a modelled stand-in for a 10 mm-aperture galvo head (about
100 x 70 mm body); the outline and the 40 mm M4 pattern are this task's own. Not a vendor file.

## The beam

The beam is the swept volume of the laser over the whole field: a cone narrowing from the field
at the work plane (z = 0) to the 30 mm lens at z = 210. The field's corners are 106 mm from the
axis, so near the bench the beam is 106 mm out, and only near the lens is it narrow. `cad tool
laser_cone focal_length=210 field=150 lens_dia=30` builds it, and so does the grader's keepout.

## The assembly: exact body names

`assembly.py` returns these bodies, with these names, in one frame: z = 0 is the bench top (the
work plane), and the beam axis is x = y = 0.

| body | what | placed |
|---|---|---|
| `bench` | built by you: `Pos(0, 0, -6) * Box(400, 300, 12)`, 400 x 300 x 12 mm | top face on z = 0, bounding-box center (0, 0, -6) |
| `galvo_head` | the given part (`bought_solid` in `cad_agent.state`), moved by translation only | STEP origin at (0, 0, 210): the lens exit is at z = 210, bounding-box center (0, 0, 252.5), the +x face at x = 50 with its holes at y = +-20, z = 240 and 280 |
| `galvo_mount` | yours: part module `parts/galvo_mount.py`, aluminium (`MATERIAL = "aluminium"`, `PROCESS = "cnc"`) | wherever your design puts it |

## What is checked

1. **Pinned bodies.** `bench` is 400 x 300 x 12 mm (bounding box, +-0.1) with its center at
   (0, 0, -6) within 0.1 mm. `galvo_head` is 100 x 70 x 85 mm (+-0.1) with its center at
   (0, 0, 252.5) within 0.1 mm.
2. **Out of the beam.** `galvo_mount` does not enter the beam cone (`laser_cone`, focal length 210,
   field 150, lens diameter 30, with its work plane at z = 0 on the beam axis, `at = [0, 0, 0]`).
   Any overlap fails.
3. **It stands on the bench.** The closest distance between `galvo_mount` and `bench` is at most
   0.05 mm. Touching counts; overlapping fails.
4. **It lies on the head.** The closest distance between `galvo_mount` and `galvo_head` is at
   most 0.05 mm, touching but not overlapping.
5. **M4 bolts.** Each of the head's four tapped M4 holes has a hole in the mount on the same axis,
   within 0.1 mm, and the pair suits an M4 screw: the mount's holes are M4 clearance holes
   (4.5 mm, see `cad tables holes`).
6. **Mass.** `galvo_mount` weighs at most 550 g, computed from its `MATERIAL`.
7. **Envelope.** Bench, head and mount together fit in 400 x 300 x 310 mm (x, y, z).

The usual `cad` gates apply on top of these: no two bodies overlap, and every part passes the
part rules for its `PROCESS` (`cad rules`; a `cnc` part has to fit a 300 x 200 x 100 mm box in
some orientation, so no dimension of the mount may pass 300 mm).

## Working

Write your own `spec.toml` first, with these requirements as `[[size]]`, `[[position]]`,
`[[keepout]]`, `[[clearance]]` (`max_mm` for "touches"), `[[interface]]`, `[[mass]]` and
`[[envelope]]` entries (`cad_agent/spec.py` has the format), then `parts/galvo_mount.py` and
`assembly.py`, then `cad check galvo_mount`. Finish with a commit, `cad verify galvo_mount` and
`cad done galvo_mount`.

## How it is graded

The grader copies your project, puts the given files and its own `spec.toml` (the list above and
nothing else) over the copy, and runs `cad verify` on it in a fresh process. Your own `spec.toml`
is not read. The score is the share of rows that pass; PASS needs every one. Rows that wait on a
person approving a render (`drift/`, `extent/`) are not counted.
