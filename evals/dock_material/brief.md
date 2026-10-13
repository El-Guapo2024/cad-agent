# dock_material: a guide rail for boards, bolted beside a 250 C hot plate

A small reflow hot plate stands on a steel base plate, and boards are slid onto it along a dock: a rail on the
base plate, a few millimetres off the plate's long edge, that guides them. Design the dock and the assembly. The
project slug is `dock_material`.

## What you get

Two bought-part STEPs, with their `.json` source notes, are already in `bought/`. They are laid in again over your
copy before grading, so editing them gains nothing. Load them with `bought_solid()` and place them; don't change
them (`cad bought info <name>` prints one's bounding box and source).

| file | body | size x, y, z | STEP origin | features |
|---|---|---|---|---|
| `hot_plate.step` | aluminium heating plate | 80 x 60 x 10 mm | centre of the underside, +z up | none: a plain plate that runs at up to 250 C |
| `base_plate.step` | base, mild steel | 140 x 120 x 6 mm | centre of the top face, so it spans z -6 to 0 | four M4 tapped holes, drilled 3.3 mm through, at (+-40, +-40) |

The base plate's `.json` also says what it is made of and declares the highest temperature it may sit at, 400 C,
with the page that gives the number.

## What to design

One part module, `parts/dock.py`, and one body named `dock`. In `assembly.py`, `parts()` returns exactly three
bodies, with these names:

`base_plate`, `hot_plate`, `dock`

- Place `base_plate` as it is: its top face is z = 0, centred on x = y = 0.
- Place `hot_plate` as it is too: it stands on the base plate, centred on x = y = 0, so its bounding-box centre is at
  (0, 0, 5). They touch on purpose: put the pair in `ALLOW_CONTACT`.
- The `dock` is a rail that stands on the base plate beside the hot plate's long edge, on either side of it. Its
  nearest point to the plate is 2.0 to 4.0 mm from it: the plate grows when it is hot, and the rule measures the
  closest approach, so that is the narrowest gap anywhere.
- It is bolted down through the base plate's holes. Every round hole of the dock whose axis lands on the base plate
  is an M4 clearance hole (4.3 to 4.8 mm) on one of the base plate's holes, within 0.1 mm of coaxial, and every hole
  of the base plate that lies under the dock has a hole of the dock on its axis. So the dock has a bolt hole where it
  covers a hole of the base, and no other round hole over the base.
- Size, x by y by z: 90 to 120 by 12 to 20 by 12 to 20 mm. The plate's top face is at z = 10, so a dock 12 mm tall
  stands 2 mm above it.
- Material: `MATERIAL` is one of the twelve materials `cad tables materials` knows: aluminium, steel, stainless,
  brass, copper, PLA, PETG, ABS, nylon, acrylic, FR4 and polyimide. Anything else, or none, leaves the dock with no
  rating, and then its heat row (below) cannot pass. Declare `PROCESS`, `MIN_FEATURE_MM` and `EXPECT_FEATURES`: a
  part whose thinnest side is under a quarter of its longest counts as a flat part, and `cad check` says how many
  cutouts it counts.
- Don't model the screws: the base plate's holes are drawn at the tap drill, so a screw would overlap it.

## What `cad verify` grades

The grader's `spec.toml` replaces yours. Every number it uses is here, and every part and assembly gate still
applies (`cad rules`), so no two bodies may interfere.

- **Bodies:** exactly three, `base_plate`, `hot_plate` and `dock`.
- **Envelope:** the whole assembly fits in 140 x 120 x 26 mm.
- **Positions:** `base_plate` bounding-box centre at (0, 0, -3) and `hot_plate` at (0, 0, 5), each within 0.1 mm.
- **Sizes:** `base_plate` 140 x 120 x 6 mm and `hot_plate` 80 x 60 x 10 mm, each within 0.1 mm; the `dock` as above.
- **Gap to the plate:** the closest distance between `dock` and `hot_plate` is 2.0 to 4.0 mm.
- **Seating:** the closest distance between `dock` and `base_plate` is at most 0.1 mm, with no overlap.
- **M4 interface**, `dock` against `base_plate` and again `base_plate` against `dock`: every hole in the first whose
  axis points at the second (on its material or in one of its holes) is coaxial with a hole of the second to within
  0.1 mm, and the pair is sized for M4: each hole is a clearance hole (4.3 to 4.8 mm), the 3.3 mm tap drill or the
  5.6 mm insert bore (those two within 0.15 mm), and at least one of the two is the clearance. A hole is judged by
  its narrowest bore, so a counterbore on the same axis is part of it. The base plate's holes are 3.3 mm, so the
  dock's bore must be 4.3 to 4.8 mm. Judging the base plate's holes too is how a base hole under the dock with no
  hole of the dock over it is caught.
- **Heat:** the plate is held at 250 C, and every body within 15 mm of it (the exact distance between surfaces, not
  between boxes) must be rated for at least 250 C: for a made body, the maximum service temperature of its
  `MATERIAL` in `cad tables materials`, which prints each number with its basis and where it came from; for a bought
  body, what its `.json` declares. The plate is the source and is exempt. It is a zone and not a thermal model: a body
  at the edge of it is held to 250 C as if it touched the plate, and an air gap or an insulator buys nothing inside
  the radius. The dock is in the zone, and so is the base plate, which declares 400 C.

## Where the numbers come from

- Hot plate: Hillesheim GmbH HAP250 aluminium heating plate, product page
  https://www.hillesheim-gmbh.com/en/products/aluminium-electric_heating_plate.php (read 2026-10-04): AlMg3
  (EN AW-5754), 10 to 20 mm thick, 250 C maximum operating temperature, bore holes and bolt threads made to order.
  The vendor publishes no drawing, so the 80 x 60 x 10 mm outline is this task's order. The STEP's `.json` repeats
  this.
- Base plate: this task's own drawing; its 400 C is what `cad tables materials` gives steel (MakeItFrom.com, ASTM A36,
  Maximum Temperature: Mechanical), and its `.json` quotes the page.
- M4 clearance 4.3, 4.5 and 4.8 mm (ISO 273 fine, medium and coarse) and tap drill 3.3 mm: `cad tables holes` and
  `cad tables taps`.

## Finish

Check the design with `cad check`, commit it, then run `cad verify dock_material` and `cad done dock_material`.
Report the verdict line, the dock's material and its rated temperature with where you got it, and any assumption you
made.
