# beam_deflection: a beam that sags no more than 50 um under 2.5 kg

A tool of 2.5 kg hangs from the middle of a beam that rests on two steel blocks 600 mm apart, and the beam may sag
no more than 50 um there. Choose the beam's section and material and write the assembly. The project slug is
`beam_deflection`.

## What you get

One bought-part STEP, with its `.json` source note, is already in `bought/`. It is laid in again over your copy
before grading, so editing it gains nothing. Load it with `bought_solid()` and place it; don't change it (`cad
bought info support` prints its bounding box and source).

| file | body | size x, y, z | STEP origin | what it is |
|---|---|---|---|---|
| `support.step` | `support_left` and `support_right` | 40 x 40 x 40 mm | its centre | a cube of mild steel, 502.4 g, which its `.json` declares with where the number comes from (the same file, placed twice) |

The tool is not a body: don't model it.

## Frame and where the given bodies go

x runs along the beam, y across it, z up. z = 0 is the bench the blocks stand on, and the beam lies along x, centred
on x = 0. The grader checks each block's bounding-box centre to 0.1 mm, and its size:

| body | centre (x, y, z) |
|---|---|
| `support_left` | (-320, 0, 20) |
| `support_right` | (320, 0, 20) |

The blocks' inner faces are 600 mm apart, so that is the span; their top faces are at z = 40.

## What to build

One body named `beam`, resting on the tops of both blocks. In `assembly.py`, `parts()` returns exactly three bodies:
`support_left`, `support_right` and `beam`.

The beam is stock, from the library: a part module is made by a process with a working volume (the `envelope` row of
`cad check`: 300 x 200 x 100 mm for `cnc`, 600 x 400 x 25 for `laser_cut`, 250 x 210 x 210 for `fdm`), so no part
module can be a bar as long as this one. `cad lib ls` lists what the library has,
and `cad lib use beam_deflection <entry> length=<mm> --as <name>` copies one into `bought/` with its mass and where it
came from. Then `bought_solid()` loads it like the given STEP, and the `axis` it runs along is a parameter of the
entry. The T-slot extrusions come twice, as their real profile and as the box of their outer size; what a rule may
read of a part is in `cad lib info`. Put the beam's bounding box on the blocks (its underside at z = 40), and let the
pairs that touch on purpose, the beam with each block, go in `ALLOW_CONTACT`.

## What `cad verify` grades

The grader's `spec.toml` replaces yours. Every number it uses is here, and every part and assembly gate still applies
(`cad rules`), so no two bodies may interfere.

- **Bodies:** exactly three, `support_left`, `support_right` and `beam`.
- **Envelope:** the whole assembly fits in 700 x 60 x 90 mm.
- **Given bodies:** `support_left` and `support_right` at the centres above, each within 0.1 mm, and 40 x 40 x 40 mm
  within 0.1 mm.
- **Size:** the `beam` is 620 to 680 mm long (x) and at most 40 x 40 mm across (y and z): it reaches over both blocks
  and fits on them.
- **Resting:** the closest distance between the `beam` and each block is at most 0.1 mm, with no overlap.
- **Mass:** the `beam` weighs at most 600 g, as its sidecar declares it (`cad lib use` prints how the library works
  it out for the length you ask for).
- **Deflection:** the beam is held as a beam supported at both blocks (simple supports) over the 600 mm span, with 2500
  g hanging from its middle and its own weight spread along it, gravity along -z, and may sag at most 50 um, at its
  middle. `cad check` computes it (Euler-Bernoulli bending from the beam's own cross-sections and the Young's modulus
  of its material in `cad tables materials`) and says what it used. Add this to your own `spec.toml` to watch the
  number as you design:

  ```toml
  [[deflection]]
  body = "beam"
  support = "simple"
  span_mm = 600
  load_g = 2500
  at = "center"
  self_weight = true
  max_um = 50
  ```

  The rule says UNCHECKED, which is not a pass, for a beam it cannot judge: a bought body that is not declared exact
  geometry, which is the box of a profile's outer size and not the profile (a solid box stands for a rail with about
  twice the stiffness of the real section), or one with no material; a section it cannot read; a span under ten times
  the section's depth.

## Where the numbers come from

- The blocks, the 2.5 kg, the 600 mm and the 50 um are this task's own. A block's mass is its 64 cm3 at the 7.85 g/cm3
  `cad tables density` gives steel.
- The beam's stiffness: Euler-Bernoulli bending, with the cases of Roark's Formulas for Stress and Strain, 8th edition,
  Table 8.1 (1e and 2e for a simple beam), as `cad_agent/beam.py` says.

## Finish

Check the design with `cad check`, commit it, then run `cad verify beam_deflection` and `cad done beam_deflection`.
Report the verdict line, the beam you chose with its deflection as `cad check` printed it, and any assumption you
made.
