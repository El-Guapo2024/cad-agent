# pinned_carrier: a carrier block that locates on two dowel pins and clears a screw head

A base plate has two dowel pins pressed in, and a screw head standing proud between them.
Design a carrier block that locates on the pins, seats flat on the base, and has a relief pocket
over the screw head. The project slug is `pinned_carrier`.

## What you get

Three bought-part STEPs, with their `.json` source notes, are already in `bought/`. They are laid
in again over your copy before grading, so editing them gains nothing. Load them with
`bought_solid()` and place them; don't change them (`cad bought info <name>` prints one's
bounding box and source).

| file | body | size x, y, z | STEP origin | features |
|---|---|---|---|---|
| `base_plate.step` | base plate, steel | 100 x 60 x 10 mm | centre of the top face, so it spans z -10 to 0 | two 4.0 mm blind holes, 6 mm deep, at (+-25, 0) for the pins; one 4.5 mm through hole at (0, 0) for the screw |
| `dowel_pin.step` | one ISO 8734 4 m6 x 16 dowel pin | 4.0 x 4.0 x 16 mm | on the axis, at the bottom end; the pin points +z | modelled at the nominal 4.0 mm, 0.63 mm end chamfers |
| `clamp_screw.step` | ISO 4762 M4 x 10 socket head cap screw | 7.0 x 7.0 x 14 mm | on the axis, at the head's bearing face; the shank points -z | head 7.0 mm across and 4.0 mm high; the shank ends at z = -10, flush with the base underside |

## What to design

One carrier part module (name it as you like), placed once. In `assembly.py`, `parts()` returns
exactly five bodies, with these names:

`base_plate`, `pin_1`, `pin_2`, `clamp_screw`, `carrier`

- Place `base_plate` and `clamp_screw` as they are: the base's top face is z = 0, centred on
  x = y = 0, and the screw's head sits on it at the origin.
- Place `dowel_pin` twice: `pin_1` with its origin at (-25, 0, -6) and `pin_2` at (25, 0, -6).
  Each is pressed 6 mm into its base hole, so 10 mm of it stands above the base.
- The `carrier` is a block 70 x 30 x 12 mm (x, y, z), long side along x, centred on x = y = 0,
  with its underside on the base's top face (z = 0).
- Two round holes, one on each pin, through the block. The hole must be at least as big as the pin
  and leave at most 0.1 mm between pin and hole wall: a diameter from 4.0 to 4.2 mm. For
  reference, ISO 286 gives a 4 m6 pin as 4.004 to 4.012 mm and a 4 H7 hole as 4.000 to 4.012 mm,
  so a pin presses into an H7 hole; a block that must lift off by hand takes an F7 or G7 hole
  (F7 is 4.010 to 4.022 mm).
- One relief pocket in the underside, concentric with the screw, so the block seats on the base
  and not on the screw head. It clears the head by at least 0.5 mm on every side and above: at
  least 8.0 mm across and 4.5 mm deep.
- The block has no other round cut: no slot, no extra mounting hole, no rounded pocket corners
  (see "Coaxial holes" below). It is made of aluminium on a CNC. There is no heat requirement.
- The usual part gates apply (`cad rules`). A 12 mm block counts as a flat part, so it needs
  `EXPECT_FEATURES`: `cad check` reports how many cutouts it finds at mid-height.

## What `cad verify` grades

The grader's `spec.toml` replaces yours. Every number it uses is here, and every part and
assembly gate still applies, so no two bodies may interfere.

- **Positions:** bounding-box centres, each within 0.1 mm: `base_plate` (0, 0, -5), `pin_1`
  (-25, 0, 2), `pin_2` (25, 0, 2), `clamp_screw` (0, 0, -3).
- **Sizes**, each within 0.1 mm: `base_plate` 100 x 60 x 10, `pin_1` and `pin_2` 4 x 4 x 16,
  `clamp_screw` 7 x 7 x 14. The `carrier` is 70 x 30 x 12 mm within 0.2 mm.
- **Location fit:** the closest distance between `pin_1` and `carrier` is at most 0.1 mm, and the
  same for `pin_2`. Any overlap fails.
- **Seats flat:** the closest distance between `carrier` and `base_plate` is at most 0.05 mm, with
  no overlap.
- **Relief pocket:** the closest distance between `carrier` and `clamp_screw` is at least 0.5 mm.
- **Coaxial holes**, `carrier` against `base_plate`: every round hole or pocket in the carrier whose
  axis points at the base, and whose middle is within 15 mm of it, is coaxial with a hole in the
  base to within 0.05 mm. The base has three holes: the pin holes at (+-25, 0) and the screw hole
  at (0, 0). So the carrier's round cuts are the two pin holes and a counterbore on the screw's
  axis. The rule cannot judge a slot (its far end has no hole under it), so this task uses two
  round holes. A pocket with rounded corners fails it too; one with square corners does not.

## Where the numbers come from

- Dowel pin: ISO 8734:1997 parallel pin of hardened steel, table row for d = 4 (m6: 4.004 to
  4.012 mm, chamfer c 0.63 mm), read at https://www.globalfastener.com/standards/detail_260.html
  and https://engineersedge.com/hardware/iso_metric_dowel_pins_13805.htm; 16 mm is a listed length.
- Screw: ISO 4762 M4, head 7.0 mm across and 4.0 mm high, 3 mm socket, read at
  https://engineersedge.com/iso_socket_head_screw.htm; 10 mm is a listed length.
- M4 clearance hole 4.5 mm: `cad tables holes`. Fit limits: ISO 286.
- The base plate and the 70 x 30 x 12 mm block are this task's own drawing.

## Finish

Check the design with `cad check`, commit it, then run `cad verify pinned_carrier` and
`cad done pinned_carrier`. Report the verdict line, the hole diameter you chose and why, and any
assumption you made.
