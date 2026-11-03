# Will it move as intended? Motion checks for the PCB fab (2026-11-03)

These are the checks that the machine moves as intended, not only that it fits. Each is a geometry run on the model
or a hand calculation from datasheet numbers. None of it replaces building and running one axis.

## 1. Collisions in motion

| Check | How | Result |
|---|---|---|
| Each axis alone, over its whole travel | `cad check` in each child (fab_stage x, y, lift; laser_bridge z; the head tools' four slides, in pcbfab) | no overlap |
| The flip's half turn, platen down | scratch `flip_sweep.py`, 10 degree steps | 7.1 mm closest (frame to platen at 90 degrees) |
| LumenPnP's gantry over its Y travel, against the whole machine | scratch `gantry_sweep.py`, 35 positions | no overlap; 3.5 mm closest (a jet over a stage post) |
| Axes together | scratch `combo_sweep.py`: the stage at corners and middle x lift up/down, against the rest; the gantry (12 positions) x each tool down in turn x the stage grid; the bridge's focus low/high x the gantry | see section 4 |
| Every body pair, at rest | scratch `fab_fit.py` | no overlap |

## 2. Motors (NEMA 17, Novanta IMS data sheet)

- Holding torque: M-1713 (34 mm) 23 N·cm, M-1715 (40 mm) 42 N·cm.
- Rotor inertia: 0.038 and 0.057 kg·cm².
- The speed-torque curves are on the data sheet's chart, which wasn't read, so the margins below are against
  holding torque.

Assumptions: moving masses from the model, plus 2.5 kg for the parts that publish no mass (the platen, the heater
and the nuts); rail friction 0.01; 1 m/s² on the stage.

| Axis | Load | Drive | Torque needed | Motor | Margin |
|---|---|---|---|---|---|
| Stage Y | 19.7 kg | SFU1204, lead 4, eff 0.9 | 0.015 N·m, plus about 0.023 to spin the screw and rotor up at 1 m/s² | 40 mm, 0.42 | about 10x |
| Stage X | 13.0 kg | SFU1204 | about 0.03 N·m | 40 mm, 0.42 | over 10x |
| Platen lift (2 screws) | 6.6 kg | Tr8x2, eff 0.35 | 0.031 N·m each | 34 mm, 0.23 | 7x |
| Bridge focus (2 screws) | 15.2 kg | Tr8x2 | 0.069 N·m each | 34 mm, 0.23 | 3.3x |
| Flip | 2.1 kg at about 120 mm radius | GT2 20T:40T | 0.048 N·m at the motor for a 2 s half turn (0.19 for 1 s) | 34 mm, 0.23 | 4.8x at 2 s; a 1 s flip is too tight |

Speeds:
- Stage at 50 mm/s: 750 rpm on the 4 mm lead.
- Critical speed (THK's formula, fixed-supported, root diameter 9.9): Y screw (545 mm) 5030 rpm, X screw 13700 rpm.
  Both are far above use.

## 3. Changes this made

- **The vertical axes take Tr8x2 (single-start), not Tr8x8.**
  - A Tr8x8's helix is 20 degrees and back-drives: the 15 kg bridge, the platen and the tools would run down when
    the motors are off.
  - A Tr8x2's 5.2 degrees is under bronze-on-steel's friction angle (about 8.5 degrees), so it holds.
  - Cost: slower moves. The platen's 135 mm drop takes 67 turns, about 7 s at 600 rpm.
  - The nut is drawn at the Tr8x8 nut's size, unconfirmed (no Tr8x2 flange nut drawing was found). Essentra's
    TR8x1.5 bronze nut is the fallback.
- **The flip takes 2 s, not 1.**
- **Each head tool has its own air slide (SMC MXH10, 39 N at 0.5 MPa against a 0.3-0.7 kg tool), not one shared
  lift.** With one lift, a tool working near the board's edge brought its neighbours down onto the flip frame's
  14 mm edge bar. The stepper, screw and rail of the shared lift are gone; the head now carries 2.6 kg of tools.

## 4. Axes together

`combo_sweep.py`, run with every combination below. "Contact" means the closest approach between two bodies that
move relative to each other.

- **A. The stage against everything else.** Stage x at -65, 0 and +65, y at -102.5, 0 and +102.5, lift up and down,
  the bridge at its lowest focus. Its parts stay clear of LumenPnP, the cabinet and the bridge. The closest is the
  frame's top, 1.0 mm under LumenPnP's nozzle rack at the stage's front-left corner.
  - It found one collision: a stage post into the top of LumenPnP's strip feeders. lumenpnp_long now leaves those
    feeders out (FAB_CLEAR) but keeps the nozzle rack.
- **B. The gantry against the stage.** The gantry at 12 points on its Y travel, all tools up or each tool down in
  turn, over the same stage grid. Nothing touches with the tools up. With one tool down, the other three stay
  clear. A lowered tool meets the frame or a post only if it is lowered outside the board, so the rule for the job
  planner is: a tool lowers only over the board.
- **C. The bridge against everything.** Focus at -10 and +10, against the gantry at its 12 points. No contact
  except its own nuts on their screws.

## 5. Not checked yet

- **LumenPnP's X axis with 2.6 kg of tools on its head.** Opulo publishes no head mass. Its head in the model is
  451 cm³ (144 solids, x 395 to 495): 0.57 kg if all PETG, 1.2 kg if all aluminium, about 1.8 kg with steel motors.
  With the tools, X moves 2.5 to 5 times its own mass. Torque is not the limit: 4.4 kg at 2 m/s² is 8.8 N on the
  belt, 0.056 N·m on a 20T GT2 pulley, against a 40 mm NEMA 17's 0.42 N·m holding. The cost is speed: at the same
  belt force, X's acceleration falls by (head + 2.6) / head, so Klipper runs X at a lower acceleration (2 m/s²)
  whenever the tools are on. The belt's allowable working tension (GT2, 6 mm) and Opulo's own X settings are not
  checked here. Lighter options:
  - one jet instead of two;
  - the dispensers on their own X carriage and motor.
- **Repeatability of the flip.** Does the frame land within a few hundredths of a millimetre of where it was? Only a
  built frame and lift can show it. The camera finds the fiducials after each flip, which corrects what is left.
- **Klipper.** The config and the job's G-code run on a simulated MCU would catch travel limits and homing order.
  This needs the electronics lane's pin map.
- **Stiffness under the laser's stitching.** The stage's settle time after each 100 mm tile move. It is a ball-screw
  stage on MGN15 rails; LPKF's comparable stage is not published.
