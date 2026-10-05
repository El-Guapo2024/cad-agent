# pcb_enclosure: a two-part box for an Arduino UNO with its USB cable plugged in

Design a base and a lid for an Arduino UNO R3 that has a USB-B cable plugged in.
The cable stays in, so the box needs a window for the plug. The board bolts to
the base on four standoffs.

Your project is called `pcb_enclosure`, and it must keep that name: assembly.py and
the parts refer to it as `SLUG = "pcb_enclosure"`, and the grader copies the project
to a folder with that name.

## Given

Two bought bodies are already in `bought/`. Each has a `.json` next to it that says where
its numbers came from. Both are laid over your project again before grading, so editing
them gains nothing.

| file | what | bounding box, mm |
|---|---|---|
| `bought/arduino_uno_r3.step` | the board: 68.58 x 53.34 outline, 1.6 PCB, four 3.20 mm mounting holes, and its tall parts as blocks (USB-B socket, DC jack, four female headers) | 74.98 x 53.34 x 12.6 |
| `bought/usb_b_plug.step` | the cable's USB-B plug housing, seated in the socket | 26.7 x 11.4 x 10.5 |

Both files are drawn in one frame. The origin is the centre of the board outline, z = 0 is
the underside of the PCB, x runs along the long edge with the USB socket toward -x, and y
runs across the board. The plug is already in its plugged-in place in that frame, with its
front face on the socket's front face. It is one block, so it stands for the plug and for
the path it takes in and out through a wall. Above the underside the DC jack is the tallest
part (12.6 mm), then the USB socket (12.4) and the headers (10.1).

Where the numbers come from:

- Board outline and the four 3.20 mm holes: Arduino UNO R3 datasheet A000066, section 5.4,
  page 12. The lower-left hole is drawn 1.3 mm nearer the edge than the upper-left one.
- USB-B socket (16.5 x 12.2 x 10.8) and DC jack (14.4 x 9 x 11): Same Sky UJ2-BH-2-TH and
  PJ-002A datasheets. Header strips are typical 8.5 mm ones.
- Plug housing (26.7 x 11.4 x 10.5): W+P Products series 826 USB 2.0 cable assemblies
  datasheet, "Housing Dimensions", USB B male.
- Read the holes from the given board, never from memory. `cad bought info pcb_enclosure
  arduino_uno_r3` prints its bounding box, and `cad_agent.spec.holes(solid)` returns each
  hole's axis point, direction and diameter, which is what the grader uses.

## What assembly.py returns

At least these four bodies, with exactly these names:

| body | what |
|---|---|
| `pcb` | `Pos(0, 0, 6.0) * bought_solid(SLUG, "arduino_uno_r3")`. The board's underside is at z = 6.0, the top of your standoffs. Its bounding box is then centred at (-3.2, 0, 12.3) with size 74.98 x 53.34 x 12.6. |
| `usb_plug` | `Pos(0, 0, 6.0) * bought_solid(SLUG, "usb_b_plug")`. Its bounding box is centred at (-54.04, 11.43, 13.0) with size 26.7 x 11.4 x 10.5. |
| `base` | yours |
| `lid` | yours |

`bought_solid` is in `cad_agent.state`. The floor and the walls go wherever you like around
these two; their z position is yours to choose.

## What is graded

`cad verify` runs the grader's spec.toml and every normal gate (`cad rules`). Every row
counts except drift, extent and visual, which need a human to approve renders. A
spec.toml of your own is replaced, so it only helps you check your work.

1. **The given bodies stay put.** `pcb` and `usb_plug` have their bounding-box centres within
   0.1 mm of the numbers above and their sizes within 0.05 mm.
2. **Standoffs.** Each of the board's four mounting holes has a hole in the base on the same
   axis, within 0.1 mm, so four M3 screws can go through the board into the standoffs.
   Only the axis is checked, not the hole size. A 2.5 mm tapping hole or a 4.0 mm heat-set
   bore is typical (`cad tables`).
3. **The board rests on the base.** The closest approach between `base` and `pcb` is 0 to
   0.5 mm.
4. **Lid clearance.** The lid is at least 1.5 mm from every part of the board, a skirt
   included if it has one.
5. **The lid sits on the base.** The closest approach between `lid` and `base` is 0 to 0.5 mm.
6. **The plug gets a window.** `base` and `lid` are each at least 1.0 mm from `usb_plug`. The
   plug block is the whole path the plug takes, so wherever a wall crosses it the opening has
   to clear it by that much.
7. **The box covers the whole board, USB socket included.** `base` and `lid` are each at
   least 76 mm by 54.5 mm in plan (x by y of their bounding boxes).
8. **Envelope.** The whole assembly, plug included, fits in 112 x 66 x 30 mm.
9. **No overlaps.** Two bodies may touch but never overlap.
10. **Part gates.** Every part builds, declares a PROCESS, and passes that process's rules
    (FDM needs walls of 0.8 mm or more). A flat part, thinner than a quarter of its longest
    side, must declare `EXPECT_FEATURES` and have at least one cutout, or its web gate cannot
    be settled.

Not graded: how the lid is held on, mass and cost.
