# SMT line: where every piece comes from

The rule for this project (Juan, 2026-11-26): see what everyone else made and mimic it; never draw our own.

| Module | Borrowed from | Licence | How it is in the CAD |
|---|---|---|---|
| Pick-and-place | LumenPnP v4, Opulo, `src/assembly.FCStd` at github.com/opulo-inc/lumenpnp | CERN-OHL-W v2 | `bought/pnp_v4.step`, Opulo's own geometry, read by `tools/fcstd_read.py` |
| Its conveyor | Opulo's 2021 conveyor prototype for the Index, `conveyor` branch of github.com/opulo-inc/lumenpnp-archive | GPL-3.0 | `bought/pnp_conveyor.step`, all 32 bodies, moved only |
| Reflow oven | NeoDen IN6 user manual s2 (outline 1020 x 507 x 350, 260 wide, 30 clear, left to right) | spec sheet | `bought/reflow_oven.py`, an envelope with its tunnel |
| Line height | DigiKey 3-zone desktop mesh-belt oven sheet 114991685: belt 300 above the bench | spec sheet | `LINE_Z` in `assembly.py` |
| Hand-over between modules | SMEMA 1.2 (front rail fixed, gap at most 9.5 mm, edge-carried) | standard | `spec.toml` holds the gap |
| Stand | none needed: any shelf (NeoDen stands the IN6 on a pedestal, manual s3.3) | | `bought/riser.py`, a box |

"LumenPnP is (c) by Opulo. This notice must be included in any distributions of this project or derivative works."
The names LumenPnP and Opulo are Opulo's marks, so the parts here are called `pnp_*`.

The two STEPs are 140 MB and 15 MB, so they are not in git. `research/borrow.py` rebuilds them from the two clones
(in `~/work/smt-references/2-open-hardware-pnp/`), and their sidecar `.json` files, which are in git, hold the
sources, licences, what was changed and each file's sha256.

## What changed from the borrowed designs, and why

- **LumenPnP:** fasteners, belts, cables, the motherboard, the strip feeders and the board holder are left out of
  the STEP (400 MB with them). The conveyor replaces the board holder.
  The two rear staging plates are also out, because the conveyor's rails and rollers run where they were. The
  strip feeders move to the front plate.
- **Conveyor, turned:** it was drawn y-up for the Index. Here it is turned z-up with its rails along x, and it
  clamps on the LumenPnP's lower side extrusions. Those are the same 20x20 V-slot it clamped on in the Index.
- **Conveyor, slid back 90 mm:** its front mounts now clear the LumenPnP's control box, which the Index didn't
  have.
- **Conveyor, seated:** each corner is moved 0.01 to 0.52 mm. Opulo's two CADs of the same frame differ by tenths
  of a millimetre, and each mount's channel is exactly 20.000 wide. `borrow.py` measures the faces and centres each
  mount's channel on its extrusion.
- **Line height:** set by the oven, not the pick-and-place. An oven can't sit lower than its own belt, so the
  pick-and-place goes on a 158 mm stand.

## Found by the checks in Opulo's prototype itself (not fixed; it was never finished)

Checked body against body inside `pnp_conveyor.step`:
- The four 608ZZ end rollers pass up through the rails' ledges, 70 to 84 mm³ each. The McMaster angle in the CAD is
  uncut, so **the ledges need a notch at each roller**. The roller tops sit level with the ledge tops. That suggests
  the rollers lift the board's edge through the notches, or carry a round belt that does. The prototype's parts list
  has no belt, so this is not settled.
- Smaller overlaps:
  - the roller washers into the rails, about 16 mm³ each;
  - the SG90 servos into the rails, 0.1 to 0.3 mm;
  - the clamp cams into the servos and clamps;
  - the back knobs into their mounts, about 0.1 mm.
- The NEMA14 is in its parts list but not placed in the CAD. How the board was driven is not drawn.

## Open, before anything is built

1. **IN6 belt height:** not published. Ask NeoDen, or measure one. `LINE_Z` and the stand both follow it.
2. **Where the IN6's belt begins along its length:** taken as its end face. The gap check (4.95 mm to the
   conveyor's nearest part, at most 9.5) holds only if that is right.
3. **LumenPnP Z reach:** the board on the conveyor sits 9.7 mm lower than on Opulo's board supports. The nozzles
   must reach it (Opulo's Z travel is to be checked).
4. **LumenPnP Y reach:** the lane runs y 270.6 to 414.5. The rear edge is near what the head reaches (estimated
   ~414 from the 550 mm Y rails). Narrow boards keep to the front rail, as SMEMA has them.
5. **Board width:** 121.7 to 143.9 at Opulo's rail spacing. The knobs change it.
6. **Next modules, borrowed the same way:** a transfer conveyor if the gap or heights differ (SuperHouse PCB
   conveyor, TAPR OHL; 3MF parts only), the SMEMA cable between modules, and the laser module.
