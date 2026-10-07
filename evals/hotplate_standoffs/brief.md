# hotplate_standoffs: four standoffs that hold a 250 C hot plate 20 mm above its base

A small reflow hot plate has to sit 20 mm above its base plate on four standoffs. Design the
standoffs and the assembly. The project slug is `hotplate_standoffs`.

## What you get

Two bought-part STEPs, with their `.json` source notes, are already in `bought/`. They are laid
in again over your copy before grading, so editing them gains nothing. Load them with
`bought_solid()` and place them; don't change them (`cad bought info <name>` prints one's
bounding box and source).

| file | body | size x, y, z | STEP origin | holes |
|---|---|---|---|---|
| `hot_plate.step` | aluminium heating plate | 100 x 100 x 10 mm | centre of the underside, +z up | four blind M3 tapped holes, drilled 2.5 mm x 7 mm deep from the underside, centres at (+-43, +-43) |
| `base_plate.step` | base | 160 x 160 x 6 mm | centre of the top face, so it spans z -6 to 0 | four 3.4 mm through holes at (+-43, +-43) |

The plate runs at up to 250 C. Its top face carries the board, so the screws come up from
under the base: through the base hole, through the standoff, into the plate's tapped hole.

## What to design

One standoff part module (name it as you like), placed four times. In `assembly.py`, `parts()`
returns exactly six bodies, with these names:

`base_plate`, `hot_plate`, `standoff_1`, `standoff_2`, `standoff_3`, `standoff_4`

- Place `base_plate` as it is: its top face is z = 0, centred on x = y = 0.
- Place `hot_plate` centred on x = y = 0 with its underside at z = 20.
- One standoff on each of the plate's four hole axes, standing from the base's top face to the
  plate's underside: each touches both and overlaps neither.
- Each standoff has one through bore, an M3 clearance hole on the plate hole's axis (3.2 to
  3.6 mm; `cad tables holes` has the 3.4 mm medium size). It has no other round hole.
- Don't model screws: a tapped hole is modelled at its drill size, so a screw would overlap
  the plate.
- Material: the standoffs must be rated for at least 250 C continuous. From `cad tables
  density` that leaves stainless, steel, brass, copper, aluminium and polyimide. PLA, PETG, ABS,
  nylon, acrylic and FR4/G10 are out. Any other material (PTFE, a machinable ceramic; PEEK is
  marginal at 250 C) needs its rated temperature and the datasheet it came from in the part's
  docstring. Prefer low conductivity, since the air gap is there to keep heat out of the base.
  Set `PROCESS = "cnc"`: nothing printed survives this. `cad verify` has no heat rule yet, so no
  row checks the material; a reviewer reads `MATERIAL` and the docstring.

## What `cad verify` grades

The grader's `spec.toml` replaces yours. Every number it uses is here, and every part and
assembly gate still applies (`cad rules`), so no two bodies may interfere.

- **Envelope:** the whole assembly fits in 160 x 160 x 36 mm.
- **Positions:** `base_plate` bounding-box centre at (0, 0, -3) and `hot_plate` at (0, 0, 25),
  each within 0.1 mm.
- **Sizes:** `base_plate` 160 x 160 x 6 mm and `hot_plate` 100 x 100 x 10 mm, each within 0.1 mm.
- **Air gap:** the closest distance between `hot_plate` and `base_plate` is at least 20 mm.
- **Seating:** every standoff is within 0.1 mm of `base_plate` and within 0.1 mm of `hot_plate`,
  with no overlap.
- **M3 interface**, each standoff against `hot_plate`: every hole in the standoff whose axis
  points at the plate, and whose middle is within 15 mm of it, is coaxial with a plate hole to
  within 0.1 mm, and the pair is sized for M3: each hole is a clearance hole (3.2 to 3.6 mm), the
  2.5 mm tap drill or the 4.0 mm insert bore (those two within 0.15 mm), and at least one of the
  two is the clearance. A hole is judged by its narrowest bore, so a counterbore on the same axis
  is part of it. The plate's holes are 2.5 mm, so the standoff's bore must be 3.2 to 3.6 mm.

## Where the numbers come from

- Hot plate: Hillesheim GmbH HAP250 aluminium heating plate, product page
  https://www.hillesheim-gmbh.com/en/products/aluminium-electric_heating_plate.php (read
  2026-10-04): AlMg3 (EN AW-5754), 10 to 20 mm thick, 250 C maximum operating temperature, bore
  holes and bolt threads made to order. The vendor publishes no drawing, so the 100 x 100 x 10 mm
  outline and the four M3 holes 7 mm from the edges are this task's order. The STEP's `.json`
  repeats this.
- M3 clearance 3.2, 3.4 and 3.6 mm (ISO 273 fine, medium and coarse) and tap drill 2.5 mm:
  `cad tables holes` has the medium size, `cad tables taps` the drill.
- The 20 mm air gap: still air between a plate over 100 C and what's under it, the default in
  the `/cad` skill.

## Finish

Check the design with `cad check`, commit it, then run `cad verify hotplate_standoffs` and
`cad done hotplate_standoffs`. Report the verdict line, the standoff material and its rated
temperature with where you got it, and any assumption you made.
