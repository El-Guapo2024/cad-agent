# idler_bracket: a bracket on the end of a 2040 extrusion that holds a GT2 idler's shaft

Design a bracket that bolts to the end of a 2040 extrusion and holds the M5
shaft of a GT2 toothless idler, so the idler spins freely. The extrusion, idler
and shaft are given. You design the bracket and write the assembly.

Your project is `idler_bracket` (that is the `SLUG` in `assembly.py`).

## Given

Already in your project's `bought/`, each a STEP with a `.json` that says where
its numbers came from. They are laid over your project again before grading, so
editing them gains nothing.

| file | body name | what it is |
|---|---|---|
| `extrusion_2040.step` | `extrusion` | a 60 mm stub of 2040 profile: 20 x 40 mm, with a 4.2 mm bore (the M5 tap drill) in its end face 10 mm either side of the centre. T-slots left out |
| `gt2_idler.step` | `idler` | GT2 20T toothless idler for a 6 mm belt: 18 mm across the flanges, 8.5 mm wide, 5 mm bore |
| `m5_shaft.step` | `shaft` | the M5 rod it runs on: a plain 5.0 x 20 mm cylinder |

The extrusion comes from `bin/cad tables` (2040: 20 x 40, 4.2 mm bore). The
idler's size is what two retailer listings agree on (botland.store product
18929, tinytronics.nl "GT2-20 pulley toothless 5mm"); no maker datasheet turned
up, and its belt-running diameter (12.2) and flange thickness (1.0) are
assumptions. The shaft is the ISO 262 nominal M5. M5 hole sizes come from
`bin/cad tables` (ISO 273 clearance 5.5, tap drill 4.2).

Each STEP is centred on its own bounding box and already turned the way the
assembly needs it, so you only translate it. `bin/cad bought info idler_bracket <name>`
prints its box.

## Frame and where the given bodies go

x runs along the extrusion, y across its 40 mm side, z up: its 20 mm side, and
the shaft's direction. The extrusion's end face is x = 0 and the stub runs back
to x = -60. Its two end bores run along x at y = ±10, z = 0. The idler and shaft
axis is the line x = 22, y = 0. The grader checks each given body's
bounding-box centre to 0.1 mm, and its size to 0.05 mm:

| body | centre (x, y, z) | size (x, y, z) |
|---|---|---|
| `extrusion` | (-30, 0, 0) | 60 x 40 x 20 mm |
| `idler` | (22, 0, 0) | 18 x 18 x 8.5 mm |
| `shaft` | (22, 0, 0) | 5 x 5 x 20 mm |

## What to build

One part module, `parts/bracket.py`, and one body named `bracket`. `assembly.py`
returns exactly four bodies: `extrusion`, `idler`, `shaft`, `bracket`. The
bracket bolts to the end face with two M5 screws into the end bores, and holds
the shaft with the idler on it.

The grader checks these, and nothing else beyond the usual gates:

1. **Bolts to the extrusion.** Two holes in the bracket on the end bores (axes
   along x at y = ±10, z = 0), each axis within 0.1 mm of its bore's, 5.3 to
   5.8 mm across (M5 clearance, ISO 273 fine to coarse; 5.5 is the medium size),
   over the 4.2 mm bore. The bracket rests on the end face: gap at most 0.05 mm,
   no overlap.
2. **Shaft holes.** Round holes in the bracket whose axes are within 0.1 mm of
   the idler's bore axis. They must also fit the shaft: the closest approach of
   the shaft to the bracket is between 0.1 and 0.5 mm, which is a hole of about
   5.2 to 6.0 mm (the 5.5 mm M5 clearance gives 0.25). The idler's bore is 5.0,
   so the checker cannot size these holes for M5 itself; the gap does it.
3. **The idler spins.** At least 0.5 mm between the idler and every face of the
   bracket.
4. **Envelope.** The whole assembly, stub included, fits in 96 x 40 x 20 mm: the
   bracket and idler reach no more than 36 mm past the end face, and the
   bracket is no wider than the extrusion (40) and no taller than it (20).

Round holes. The checker reads every round hole in the bracket whose axis line
passes through the extrusion's or the idler's bounding box (plus 0.5 mm all
round) as a mounting or shaft hole, and wants a matching hole there. So over
those two boxes the bracket has the two mounting holes and the shaft holes and
no other hole: a lightening hole would have nothing under it. A counterbore or
nut trap shares its hole's axis and is part of that hole, judged by its narrowest
bore, so it is fine on a shaft hole and on a mounting hole alike. A slot is
judged by its centre line, which has to pass over the matching hole, and the
rounded corners of a pocket are not holes. The idler's box ends at y = ±9, so
the mounting holes at y = ±10 stay clear of it.

## Also expected, not scored

Hold the shaft at both ends, one arm on each side of the idler. The checks
cannot tell one arm from two, but a cantilevered idler is a poor bracket.

## The usual gates

Everything `cad verify` prints counts, except the visual rows (they need a human
to approve renders). Declare `MATERIAL`, `PROCESS` and
`MIN_FEATURE_MM` in the part. Pairs that touch on purpose (bracket and
extrusion, idler and shaft) go in `ALLOW_CONTACT`. Write your own `spec.toml`
too; the grader replaces it with its own.
