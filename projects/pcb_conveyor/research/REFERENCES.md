# Reference designs for the conveyor

Our design meshes proven features from these. Each entry: where it comes from, its license or status, what we
observed, and what we take. Vendor photos are linked, not copied (their copyright).

## NeoDen J08 SMT conveyor (commercial)

- Source: https://neoden-solution.com/products/j08-smt-conveyor (photos: SMT_Conveyor.jpg end view,
  Conveyor.jpg top view of the rails, Conveyor_SMT.jpg control panel; listed $699-739, 2026-11-26).
- Status: commercial product; we redraw from observation, copy no drawings.
- Observed (from photos, no measurements yet):
  - Rails: long hollow aluminium extrusions. A narrow belt (orange/brown) rides the inner top lip; the return
    run passes below on small idler wheels bolted to the rail.
  - Width: two trapezoidal lead screws (one near each end) plus round guide rods beside them, in aluminium
    shaft-support blocks; adjusted by a hand wheel at one end.
  - Drive: a gear motor hanging below the middle of the frame, a shaft across to a pulley under each rail; two
    small snub idlers around each drive pulley (more belt wrap, keeps the belt off the shaft).
  - Frame: folded, painted sheet steel; C-shaped legs with foot plates and levelling feet; a bottom shelf;
    rounded end covers over the top housing.
  - Controls: side box with an AC motor speed controller (US-52 class), power switch and lamp, a pass-through /
    inspection mode switch, a jog button; photoelectric sensors (M18 class, blue) at both ends; the rails'
    end brackets carry the SMEMA cables.
- Take: the extruded rail with hidden belt return; the motor under the middle; snub idlers at the drive pulley;
  round guide rods (cheaper, dirt-tolerant) as an option to the MGN guides; the hand wheel as a fallback to the
  width motor; end photo-eyes; the control box layout (speed, mode, jog).

## SuperHouse PCBCONVEYOR (open hardware, TAPR OHL v1.0)

- Source: https://github.com/SuperHouse/PCBCONVEYOR (commit aa8a56e, 2025-11-25). Credited in ../CREDITS.md.
- Observed: 1 in square tube frame with printed corner plugs; belt on 18 mm flanged printed pulleys; one rail
  on an MGN7 rail, width by stepper + GT2 belt with a limit switch for homing; ESP32 touch controller with two
  stepper drivers, SMEMA in/out, CAN; firmware with G-code width commands.
- Take: motorised, homed width (G-code style commands suit the line OS); SMEMA handshake logic; sensors at both ends.

## SMEMA Mechanical/Electrical Interface Standard 1.2

- Source: SuperHouse repo, Resources/smema1.2.pdf.
- Take: board bottom 37-38 in, front rail fixed, edge clearance <= 0.187 in, tooling pins 0.156 in at 0.300 in
  from the front edge, gap <= 0.375 in, lead-in >= 0.125 in; Board Available / Machine Ready dry contacts
  (30 V, 10 mA, 50 ms minimum open), 14-pin connector, 1/4-20 earth stud each side.

## Still to add

- A teardown of a bought reference unit (needs Juan's OK to buy): rail profile section, belt type and size,
  pulley sizes, screw pitch, motor.
- LumenPnP (how our conveyor passes through its bed), the UV laser station, reflow ovens.
