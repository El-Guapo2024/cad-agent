# mgn12h_carriage: the carriage plate of a linear axis, on an MGN12H block between two end stops

Design the carriage plate of a linear axis. It bolts onto a HIWIN MGN12H block,
carries a tool flange, and travels with the block 40 mm either way along an
MGN12 rail between two end stops. The rail, block, stops and tool flange are
given. You design the plate and write the assembly.

Your project is `mgn12h_carriage` (that is the `SLUG` in `assembly.py`).

## Given

Already in your project's `bought/`, each a STEP with a `.json` that says where
its numbers came from. They are laid over your project again before grading, so
editing them gains nothing.

| file | body name | what it is |
|---|---|---|
| `mgn12_rail.step` | `rail` | HIWIN MGNR12R rail, 150 x 12 x 8 mm, six counterbored holes, 25 mm pitch |
| `mgn12h_block.step` | `block` | HIWIN MGN12H block, 45.4 x 27 x 10 mm, with the rail channel and four tapped M3 holes (2.5 mm, 3.5 deep) on 20 x 20 mm |
| `end_stop.step` | `stop_left`, `stop_right` | an 8 x 24 x 20 mm stop butted against each rail end (the same file, placed twice) |
| `tool_flange.step` | `tool` | 36 x 36 x 6 mm tool flange: four 3.4 mm holes on 30 x 30 mm, and a 26 x 26 x 3 mm relief in its underside for the heads of the plate's own screws |

Block and rail dimensions come from the HIWIN MG series catalog
GW-11-5-EN-2207-K: table 3.79 (MGN12H: H 13, H1 3.0, W 27, B 20, C 20, L 45.4,
M3 x 3.5) and table 3.81 (MGNR12R: 12 x 8, pitch 25). The stops and the flange
are fixtures made for this task. M3 hole sizes come from `bin/cad tables`
(ISO 273 clearance 3.4, tap drill 2.5, heat-set bore 4.0).

Each STEP is centred on its own bounding box and already turned the way the
assembly needs it, so you only translate it. `bin/cad bought info mgn12h_carriage <name>`
prints its box.

## Frame and where the given bodies go

x runs along the rail, y across it, z up. z = 0 is the surface the rail is
screwed to. `parts()` returns the home pose, with the block in the middle of the
rail. The grader checks each given body's bounding-box centre to 0.1 mm, and its
size:

| body | centre (x, y, z) |
|---|---|
| `rail` | (0, 0, 4) |
| `block` | (0, 0, 8) |
| `stop_left` | (-79, 0, 10) |
| `stop_right` | (79, 0, 10) |
| `tool` | (0, 0, 24) |

The rail runs from x = -75 to 75 and each stop's inner face butts a rail end.
The block's top face is z = 13.

## What to build

One part module, `parts/carriage_plate.py`, and one body named `carriage_plate`.
`assembly.py` returns exactly six bodies: `rail`, `block`, `stop_left`,
`stop_right`, `tool`, `carriage_plate`.

The grader checks these, and nothing else beyond the usual gates:

1. **Bolts to the block.** Four M3 holes in the plate at x = ±10, y = ±10 (the
   block's 20 x 20 pattern). Each axis is within 0.1 mm of the block's hole
   under it, and each hole is the 3.4 mm M3 clearance (within 0.15 mm) over the
   block's tapped 2.5.
2. **Seats on the block.** The plate's underside rests on the block's top
   face, z = 13: gap at most 0.05 mm, no overlap.
3. **Carries the tool.** Four M3 holes at x = ±15, y = ±15 (30 x 30, centred on
   the block). Each axis is within 0.1 mm of the tool's hole above it, and each
   hole is a heat-set insert bore (4.0 mm), a tapped-drill hole (2.5) or a
   clearance hole (3.4), within 0.15 mm. The tool rests on the plate's top
   face: gap at most 0.05 mm, no overlap.
4. **Size.** 8.0 mm thick, within 0.05 (that fixes where the tool sits, and a
   5.7 mm insert needs the depth); 40 to 66 mm along x; 40 to 60 mm along y. The
   40 leaves 3 mm of material beyond each tool bore, and the 66 is what the
   travel leaves between the stops.
5. **Clears the rail.** At least 3 mm between the plate and the rail.
6. **Travel.** 40 mm either way from home, with 2 mm to spare at each end: at
   home the plate must be at least 42 mm from each stop.
7. **Mass.** At most 30 g, from your part module's `MATERIAL` density
   (`bin/cad tables`).

**Round holes.** The checker reads every round hole in the plate whose axis line
passes through the block's bounding box (45.4 x 27 x 10 mm, plus 0.5 mm all
round) as a bolt hole, and wants the block's hole under it. So over the block
the plate has the four bolt holes and nothing else round: no lightening holes,
no rounded pockets, and no counterbores (a counterbore is a wider hole on the
same axis, and fails the size check). The screw heads sit on the plate's top
face, inside the tool flange's relief. The tool bores, at y = ±15, are outside
that box.

## Declare the travel

Declare the axis in `assembly.py` (format in `cad_agent/motion.py`):

```python
AXES = {"x": {"moves": ("block", "carriage_plate", "tool"), "direction": (1, 0, 0),
              "travel": (-40.0, 40.0), "work": (-40.0, 40.0)}}
```

The sweep gate then drives those three bodies through the whole 80 mm (seven
poses, both ends included) and fails the run if any touches a stop. Put 2.0 mm
for the plate and the tool against each stop in `CLEARANCE`, so the sweep holds
the margin. Item 6 is the same limit measured at home; the sweep is how the
whole travel gets checked.

## The usual gates

Everything `cad verify` prints counts, except the visual rows (they need a human
to approve renders). Declare `MATERIAL`, `PROCESS`, `MIN_FEATURE_MM` and
`EXPECT_FEATURES` (the plate is flat, so the web rule counts its cutouts). Pairs
that touch on purpose (plate and block, plate and tool, rail and stops) go in
`ALLOW_CONTACT`. Write your own `spec.toml` too; the grader replaces it with its
own.
