# SMT line: where every piece comes from

The rule for this project (Juan, 2026-11-26): see what everyone else made and mimic it; never draw our own.

| Module | Borrowed from | Licence | How it is in the CAD |
|---|---|---|---|
| Pick-and-place | LumenPnP v4, Opulo, `src/assembly.FCStd` at github.com/opulo-inc/lumenpnp | CERN-OHL-W v2 | `bought/pnp_v4.step`, Opulo's own geometry, read by `tools/fcstd_read.py` |
| Its conveyor | Deltaprintr's Rapid Star PCB conveyor, `Mechanics/Machine Assembly v27.step` at github.com/Deltaprintr/Rapid-Star (two `Conveyer` sub-assemblies: 2020 x 640 rail, N20 drive, 4 mm flat belt, 5 pulleys, guide, hoods, servo gripper, limit switch, stop solenoid) | CC BY-NC-SA 4.0, and Deltaprintr's permission (Juan, 2026-11-27) | `bought/pnp_conveyor.step`, 40 bodies, moved only (fasteners and corner brackets left out) |
| Conveyor rail blocks | any 20 x 20 x 23 block, one under each rail end | | `rail_blocks` in `assembly.py`, from `bought/riser.py` |
| Reflow oven | NeoDen IN6 user manual: s2 outline (1020 x 507 x 350, 260 wide, 30 clear, left to right); side profile, belt and end pockets measured off its s3.1 front photo and its entrance photo, scaled to the outline | manual and photos | `bought/reflow_oven.py` |
| Line height | the LumenPnP on its own feet, Rapid Star's belts on 23 mm blocks: board 180.1 above the bench | both CADs | `LINE_Z` in `assembly.py` |
| Hand-over between modules | SMEMA 1.2 (front rail fixed, gap at most 9.5 mm, edge-carried) | standard | `spec.toml` holds the gap |
| Oven stand | any 114.1 block, so the IN6's belt (66 above its bottom) meets the board (NeoDen stands the IN6 on a pedestal, manual s3.3) | | `bought/riser.py`, a box |

"LumenPnP is (c) by Opulo. This notice must be included in any distributions of this project or derivative works."
Rapid Star conveyor by Deltaprintr (deltaprintr.com), CC BY-NC-SA 4.0, used with Deltaprintr's permission. Its
licence asks that adaptations carry the same licence. LumenPnP, Opulo, Deltaprintr and Rapid Star are their owners'
marks, so the parts here are called `pnp_*`.

**Deltaprintr's permission:** Juan got it on 2026-11-27. Its exact terms (which parts, and whether it covers selling)
are not on file here yet. Save the email in `~/work/smt-references/9-line-and-conveyor/deltaprintr-rapid-star/`.

The two STEPs are 140 MB and 48 MB, so they are not in git. `research/borrow.py` rebuilds them from the LumenPnP
clone (`~/work/smt-references/2-open-hardware-pnp/lumenpnp-src/repo`) and the Rapid Star one
(`~/work/smt-references/9-line-and-conveyor/deltaprintr-rapid-star`), and their sidecar `.json` files, which are in git, hold the
sources, licences, what was changed and each file's sha256.

## What changed from the borrowed designs, and why

- **LumenPnP:** fasteners, belts, cables, the motherboard, the strip feeders and the board holder are left out of
  the STEP (400 MB with them). The conveyor replaces the board holder.
  The two rear staging plates are also out, because the conveyor's rails and rollers run where they were. The
  strip feeders move to the front plate.
- **Conveyor, swapped (v0.3):** Opulo's 2021 prototype never had its drive drawn (open item 1 of v0.2). Rapid
  Star's conveyor is the only open design found with the drive fully drawn, so it replaces it whole.
- **Conveyor, turned and placed:** Rapid Star is drawn y-up. Here it is turned z-up with its rails along x. Its
  front guide sits where Opulo's prototype had its front wall (y 270.6, clear of the control box), and its back rail
  143.9 behind it for a 140-wide board. Rapid Star's own spacing is fixed; ours is set for our board.
- **Conveyor, on blocks:** Rapid Star rests each rail end straight on its side extrusions, 640 apart, with corner
  brackets. The LumenPnP's are 600 apart. Each guide plate hangs 21.6 below its rail at 220 to 280 from the middle,
  where it carries the lower pulleys. On the LumenPnP the +x one lands on the right side extrusion. So each rail end
  stands on a bought 23 mm block.
- **Guide plates, cut 2.2 mm short at the oven end:** the only Rapid Star part changed, with Deltaprintr's
  permission, so the belts reach within 8.0 of the oven's roller (see open item 1).
- **Front limit switch, slid 5 mm:** lifted, the front rail's switch board reaches the LumenPnP's upper left side
  extrusion. It bolts to the rail's T-slot, so it slides along the rail to clear it by 1 mm.
- **Line height:** the LumenPnP stands on the bench as Opulo built it. Its board sits 180.1 above the bench.
  The IN6's belt is 66 above its own bottom, so the oven goes on a 114.1 block. (v0 had used the 300 mm belt
  height of a different oven and put the PnP on a 158 mm shelf.)

## Open, before anything is built

1. **How the board crosses to the oven:**
   - The LumenPnP's right Y motor sticks out to x 641.8, 42 mm past the frame, at 194 to 265 above the bench.
     The oven's end cap reaches that height, so the oven stands 3.2 clear of the motor.
   - Rapid Star's rails are 640 long, 40 more than the LumenPnP's frame, so they reach past the motor into the
     oven's entry pocket. Their guide plates ran 9.1 past the belts, which kept the belts 10.2 from the IN6's end
     roller, over SMEMA's 9.5. With Deltaprintr's permission each guide is cut 2.2 mm short at the oven end. Now the
     belts end **8.0 from the roller** and the guides 1.05 short of it. The roller's place is photo-measured
     (+-8 mm), so measure a real IN6 before cutting the guides.
   - The board is driven: each rail's N20 turns its belt, as Rapid Star does it.
2. **IN6 belt height and pockets:** measured off photos, to about +-8 mm. Measure a real one.
3. **LumenPnP Z reach and head clearance:** the board on the belts sits at z 80.1 in the LumenPnP's frame,
   about 29 mm higher than on Opulo's own board supports (z 51.4). The nozzles reach it more easily. The head, the cameras and the
   hoods (1.4 above the board) must still clear each other at travel height, and the top camera refocused.
4. **LumenPnP Y reach:** the lane runs y 270.6 to 414.5. The rear edge is near what the head reaches (estimated
   ~414 from the 550 mm Y rails). Narrow boards keep to the front rail, as SMEMA has them.
5. **Board width:** set by where the back rail is bolted (143.9 guide to guide, a 140 board). Rapid Star has no
   width knob. Boards ride on 4 mm belts, so the edges need about 4 mm free of parts.
6. **How the rails fasten to the blocks and extrusions:** not drawn. Rapid Star's corner brackets are for its own
   frame.
7. **Electronics:** Rapid Star drives the N20s, the servos and the solenoid from its own board (`Electronics/Conveyor`,
   `OpenPNP Settings/machine.xml` "Conveyor Belt" and "Conveyor Grip"). The LumenPnP's board needs spare outputs
   for them.
8. **Next modules, borrowed the same way:** a transfer conveyor if the gap or heights differ (SuperHouse PCB
   conveyor, TAPR OHL; 3MF parts only), the SMEMA cable between modules, and the laser module.
