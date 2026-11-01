# Desktop PCB fab: electronics brief (for the EE design), 2026-11-01, UV laser

This replaces the 2026-10-28 brief (CoreXY machine with a tool changer, drill spindle): that machine was dropped.
It also replaces the first 2026-11-01 version: the 20 W fiber laser is now a 5 W 355 nm UV laser, as CircuitJet IV
and LPKF's ProtoLaser U4 use (UV ablates copper cleanly; copper reflects most 1064 nm light).

## The machine now

One machine: Opulo's LumenPnP v4.2.0 with its Y axis 300 mm longer (`projects/lumenpnp_long`), and
`projects/pcbfab` adds:

- **pnp zone (front):** a 150 x 150 hot plate under the head for reflow (tin-bismuth solder, plate capped at 240 C)
  and the via-paste cure (160 C, 30 min). Mains is 120 V (US).
- **laser zone (back):** a JPT Lark 355 nm UV laser in line with an SG7110 galvo (UV mirrors) and a 355 nm F160 lens,
  hanging from a bridge over a vacuum laser bed. The laser drills, etches, opens the solder mask over the pads, and
  marks the legend.
- **head:** LumenPnP's own head (nozzles, cameras), plus a solder-paste dispenser. Three 395 nm UV lamps on the back of
  the gantry sweep the board (as Y moves) to cure the solder mask.
- **enclosure** around the whole machine: aluminium panels, a door with a 355 nm laser-safe window, and a fume port
  to a HEPA + carbon extractor.

Process (CircuitJet's order): drill (laser); via paste squeegeed and pulled through by the vacuum bed, cured on the hot
plate; then etch (laser, which also clears paste smear off the copper). Then mask coated (by hand), UV-cured by the
gantry's lamps, and opened over the pads and marked by the laser. Then paste, place and reflow. The flip is by hand
onto two registration pins; the camera finds the board's fiducials after every move.

## Architecture

- **Host:** NVIDIA Jetson Orin Nano runs Klipper + Moonraker (motion, heaters, I/O), the cameras and AOI, the laser
  job (EZCAD-class software or MeerK40t driving the galvo controller over USB), and the MCP server the agent uses.
- **Motion MCU:** a Klipper board for LumenPnP's steppers and I/O, replacing Opulo's control box. LumenPnP's own
  motors, nozzles and cameras stay as Opulo specifies; take the counts from Opulo's BOM.
- **Galvo and laser controller:** JCZ LMCV4 (or equivalent EZCAD-class board) on USB to the Jetson. It drives the
  SG7110 galvo (XY2-100) and the UV laser's control port (pinout from the Lark manual).

## Loads and sensors (new or changed)

| Subsystem | Part | Electrical |
|---|---|---|
| UV laser | JPT Lark-355-5A, 5 W 355 nm, air cooled, built-in PSU | Mains (a complete 5 W machine built on it is listed at under 500 W total); enable / gate / frequency and alarm from the JCZ board; its fans need free air |
| Galvo | SG7110, 10 mm aperture, UV mirrors | Its driver's supply (commonly +/-15 V; check the unit), XY2-100 from the JCZ board |
| Hot plate | Misumi MPHK-150-150 500 W mica heater wound for **120 V**, capped at **240 C** (tin-bismuth solder for the demo) | Omron G3NA-210B SSR on its Y92B-N50 heatsink; RS PRO PT1000 3 x 100 mm (400 C) in a bore in the plate's edge + Adafruit MAX31865 (#3648); Selco ORA-500-QC cut-out (opens 249-271 C) on the plate's other edge, in series with the heater |
| Via vacuum bed | SainSmart 24 V vacuum pump, 42 W, -85 kPa | 24 V switched (relay or MOSFET), plus a valve to release the board |
| UV mask cure | 3 x LedWV 100 W 395 nm LED lamps, on the gantry (moving with Y) | 48 V 3 A each (9 A total), enable/PWM from the MCU, lamp fans; off unless the door is shut; cable along the X chain |
| Height sensing | Laser distance sensor on the head (to pick) | Focus and board flatness, as CircuitJet does |
| Solder paste | Dispenser on the head (auger stepper or pneumatic valve) | One stepper, or a valve + regulator |
| Pick-and-place | LumenPnP's nozzles, vacuum, cameras | As Opulo's design |
| Cameras / AOI | LumenPnP's top and bottom cameras | USB to the Jetson |
| Fume extraction | HEPA + carbon extractor | Relay; on whenever the laser, UV lamps or reflow run |
| Enclosure | Door switches (two, redundant), key switch, e-stop | Part of the laser and UV interlock |

## Safety (hardware, not software)

- The 5 W UV laser is Class 4: an invisible beam that can blind instantly. Wire the two door switches in series with
  the key switch and e-stop to the laser's hardware interlock / enable (through a safety relay), not only to the MCU.
  The UV lamps go on the same chain.
- The window is OptoSigma YL-510C-Y2(5): OD 8 at 355 nm.
- The hot plate's Selco ORA-500-QC cut-out is independent of the controller.
- Mains (UV laser, hot plate, PSUs) is fused, earthed and separated from low voltage.

## Power (estimate, to size by the EE)

- Mains: UV laser (its own PSU), hot plate (500 W via SSR), extractor.
- 24 V: motion, vacuum pump, fans, paste dispenser.
- 48 V 9 A: the three UV lamps (their own supply or drivers).
- Galvo supply as its driver needs.
- 5 V / Jetson supply.

## Agent interface

An MCP server on the Jetson wraps Moonraker and the laser job: `machine_status`, `home`, `run_step` (drill, via fill,
cure, etch, mask cure, mask open, legend, paste, place, reflow), `camera_snapshot`, `pause`, `abort`. A person approves
the steps that need hands (the flip, the mask coat, loading parts). The agent can never override the interlocks.

## Open questions for the EE

1. The galvo driver's supply voltage; the UV laser's control pinout and mains draw (from the units' manuals).
2. Solder-paste dispenser: auger or pneumatic.
3. Which laser distance sensor.
