# laser_panel: a laser-cut front panel for a button and an OLED

Design the front panel of a small control box: one sheet of 3 mm acrylic (or plywood), cut on a laser,
that screws onto a given frame and carries a push button and a 0.96 inch OLED display. You design one
part, `panel`, and the `assembly.py` that puts it with three given bodies. Everything the grader checks
is listed here, in numbers.

## What exists

Your project `laser_panel` already holds three given bought parts (do not `cad init` it, and keep that
slug: the grader rebuilds the project under that name). Each has its source in the `.json` beside it.

| body | what it is | where its size comes from |
|---|---|---|
| `frame` | the box's front frame: a 100 x 60 x 8 mm rim with an 80 x 40 mm opening, outer corners R5, and four blind M3 tapped holes in its front face (2.5 mm tap drill, 6 mm deep) at x = +-45, y = +-25 | this brief; the tap size is from `cad tables taps` |
| `push_button` | a 16 mm panel-mount momentary push button, as an envelope: a threaded barrel 15.56 mm round with two flats 14.89 mm apart (axis along z, flats facing +-y), 18.7 mm long; a 13 mm cap 5.0 mm proud of the panel; solder tabs behind | Adafruit 16mm Panel Mount Momentary Pushbutton, product 1502: its technical details (shaft 14.89 x 15.56 x 18.7, button height 5, max 18.06 x 18 x 29.4) and its R13 drawing (M16 x 1.0, cap 13.0) |
| `oled` | a 0.96 inch 128x64 OLED module: a 27.3 x 27.3 x 1.0 mm PCB with four 2.5 mm holes, a 26.7 x 19.26 x 1.37 mm glass centred on its front, header pins 7.5 mm behind it | Winstar WEA012864D-03 datasheet: General Specification and Contour Drawing |

The files are `bought/frame.step`, `bought/push_button.step` and `bought/oled.step`. They are laid again
over your project before scoring, so editing them gains nothing. Use them as they are:
`Pos(x, y, z) * bought_solid("laser_panel", name)`, with no rotation and no scaling.

The button's flange (18.06 mm) and its mounting nut bear on the panel's front and back faces, and the OLED
is held behind the panel by tape. None of that is modelled, so nothing but the cutout stands between a
component and the panel. The glass outline is +-0.2 mm in the datasheet; the model is the nominal.

## The assembly: exact body names

`assembly.py` returns bodies named exactly `frame`, `push_button`, `oled` and `panel` (more are fine; they
count toward the envelope), in one frame: +z points at the user, x to the right, y up, in mm. Each given
STEP has its origin at the middle of its bounding box, so place it with `Pos(centre)`:

| body | what | placed |
|---|---|---|
| `frame` | the given part | bounding-box centre (0, 0, -4): front face at z = 0, back face at z = -8 |
| `push_button` | the given part | bounding-box centre (-22.5, 0, -6.7): barrel axis at x = -22.5, y = 0, and the panel's front face, z = 3, meets the barrel |
| `oled` | the given part | bounding-box centre (17.5, 0, -4.365): PCB front face at z = -0.8, glass front at z = +0.57 so the glass reaches 0.57 mm into the panel, header on the +y side |
| `panel` | yours: part module `parts/panel.py`, `PROCESS = "laser_cut"` | on the frame's front face: it fills z = 0 to 3 |

## What is checked

1. **The sheet.** `panel` is 100 x 60 x 3 mm: the frame's outline, cut from 3 mm sheet. Its bounding box
   may be 0.5 mm off in x and in y and 0.1 mm off in z: 99.5 to 100.5, 59.5 to 60.5 and 2.9 to 3.1 mm.
2. **It sits on the frame.** The closest distance between `panel` and `frame` is at most 0.05 mm: its back
   face lies on the frame's front face. Touching counts; overlapping fails.
3. **M3 mounting.** Four holes in `panel` line up with the frame's four tapped holes: each axis within
   0.1 mm of a frame hole's axis, each sized as an M3 clearance hole, 3.4 mm +-0.15 (`cad tables holes`),
   over the frame's 2.5 mm tapped hole. Any hole in the panel that lies within 6 mm of the frame counts
   as a mounting hole and has to line up the same way, so the panel has no other holes near the frame.
   At the positions above, the button hole and the window are more than 8 mm from it.
4. **The button hole.** The closest distance between `push_button` and `panel` is between 0.10 and 0.40 mm.
5. **The OLED window.** The closest distance between `oled` and `panel` is between 0.10 and 0.40 mm. The
   glass reaches into the panel, so the window clears the whole glass outline, not just the visible area.
   "Closest distance" is what `bin/cad measure laser_panel oled panel --posed` prints, so a rounded window
   corner counts and any overlap fails.
6. **The given bodies are the given bodies.** Bounding-box sizes within 0.05 mm of: `frame` 100 x 60 x 8,
   `push_button` 15.56 x 14.89 x 29.4, `oled` 27.3 x 27.3 x 9.87. Bounding-box centres within 0.05 mm of
   the table above.
7. **Envelope.** The whole assembly's bounding box is at most 100.5 x 60.5 x 29.6 mm and at least
   99.5 x 59.5 x 29.2 mm. The frame and the button already make it 100 x 60 x 29.4, so a panel that
   overhangs the frame, or anything extra that sticks out, breaks it.

The usual `cad` gates apply on top: no two bodies overlap, and `panel` passes the part rules for
`laser_cut` (`cad rules`), which include 1.5 mm of material between cutouts and between a cutout and an
edge, and the cutout count it declares in `EXPECT_FEATURES`. Acrylic is the material `cad` has a density
for. Model the cut outline as it should come out: the checks apply no kerf compensation.

## Working

Write your own `spec.toml` first, with these requirements as `[[size]]`, `[[position]]`, `[[clearance]]`
(`min_mm` and `max_mm` for a gap that has to stay in a range), `[[interface]]` and `[[envelope]]` entries
(`cad_agent/spec.py` has the format), then `parts/panel.py` and `assembly.py`, then `cad check laser_panel`.
Finish with a commit, `cad verify laser_panel` and `cad done laser_panel`. Report the numbers you
measured, the choices you made, and anything you could not close.

## How it is graded

The grader copies your project, puts the given files and its own `spec.toml` (the list above and nothing
else) over the copy, and runs `cad verify` on it in a fresh process. Your own `spec.toml` is not read. The
score is the share of rows that pass; PASS needs every one. Rows that wait on a person approving a render
(`drift/`, `extent/`, `visual/`) are not counted, so leave the approving to a person.
