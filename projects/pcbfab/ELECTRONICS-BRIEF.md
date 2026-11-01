# Desktop PCB fab: electronics brief (for the EE design), 2026-11-01

This replaces the 2026-10-28 brief (CoreXY machine with a tool changer, drill spindle): that machine was dropped.

## The machine now

One machine: Opulo's LumenPnP v4.2.0 with its Y axis 300 mm longer (`projects/lumenpnp_long`), and
`projects/pcbfab` adds:

- **pnp zone (front):** a 150 x 150 hot plate under the head for reflow and the via-paste cure (160 C, 30 min).
- **laser zone (back):** a fixed galvo and F160 lens on a bridge over a vacuum laser bed, with the fiber source on the
  table under it. The laser drills, etches, opens the solder mask over the pads, and marks the legend.
- **head:** LumenPnP's own head (nozzles, cameras), plus a solder-paste dispenser. Three 395 nm UV lamps on the back of
  the gantry sweep the board (as Y moves) to cure the solder mask.
- **enclosure** around the whole machine: aluminium panels, a door with a 1064 nm laser-safe window, and a fume port
  to a HEPA + carbon extractor.

Process: drill and etch (laser), then via paste squeegeed and pulled through by the vacuum bed, cured on the hot plate.
Then mask coated (by hand), UV-cured by the gantry's lamps, and opened over the pads and marked by the laser. Then paste,
place and reflow. The flip is by hand onto two registration pins.

## Architecture

- **Host:** NVIDIA Jetson Orin Nano runs Klipper + Moonraker (motion, heaters, I/O), the cameras and AOI, the laser
  job (MeerK40t driving the galvo controller over USB), and the MCP server the agent uses.
- **Motion MCU:** a Klipper board for LumenPnP's steppers and I/O, replacing Opulo's control box. LumenPnP's own
  motors, nozzles and cameras stay as Opulo specifies; take the counts from Opulo's BOM.
- **Galvo and laser controller:** JCZ LMCV4 (or equivalent EZCAD-class board) on USB to the Jetson. It drives the
  SG7110 galvo (XY2-100) and the laser's DB25 control.

## Loads and sensors (new or changed)

| Subsystem | Part | Electrical |
|---|---|---|
| Fiber laser | JPT M7 20 W MOPA (YDFLP-E-20-M7-S-R) | 24 V DC (check the manual for the current), DB25 to the JCZ board: enable, PWM, pulse width, alarm |
| Galvo | SG7110, 10 mm aperture | Its driver's supply (commonly +/-15 V; check the unit), XY2-100 from the JCZ board |
| Hot plate | Misumi MPHK-150-150 500 W mica heater, to 250 C | Mains through an SSR (Fotek class); PT1000 + MAX31865; KSD301 hardware cut-out (pick a trip temperature above 250 C, below the heater's 300 C) |
| Via vacuum bed | SainSmart 24 V vacuum pump, 42 W, -85 kPa | 24 V switched (relay or MOSFET), plus a valve to release the board |
| UV mask cure | 3 x LedWV 100 W 395 nm LED lamps, on the gantry (moving with Y) | 48 V 3 A each (9 A total), enable/PWM from the MCU, lamp fans; off unless the door is shut; cable through the X chain's side |
| Solder paste | Dispenser on the head (auger stepper or pneumatic valve) | One stepper, or a valve + regulator |
| Pick-and-place | LumenPnP's nozzles, vacuum, cameras | As Opulo's design |
| Cameras / AOI | LumenPnP's top and bottom cameras | USB to the Jetson |
| Fume extraction | HEPA + carbon extractor | Relay; on whenever the laser, UV lamp or reflow runs |
| Enclosure | Door switches (two, redundant), key switch, e-stop | Part of the laser and UV interlock |

## Safety (hardware, not software)

- The 20 W fiber laser is Class 4: an invisible beam that can blind instantly. Wire the two door switches in series
  with the key switch and e-stop to the laser's hardware interlock / enable (through a safety relay), not only to the
  MCU. The UV lamp goes on the same chain.
- The window is Phillips ALS-YAG (OD 6+ at 1064 nm). Plain acrylic does not stop 1064 nm.
- The hot plate's KSD301 cut-out is independent of the controller.
- Mains (hot plate, PSUs) is fused, earthed and separated from low voltage.

## Power (estimate, to size by the EE)

- 24 V: motion, laser source, vacuum pump, fans, paste dispenser.
- 48 V 9 A: the three UV lamps (their own supply or drivers).
- Galvo supply as its driver needs.
- 5 V / Jetson supply.
- Mains: hot plate (500 W via SSR), extractor.

## Agent interface

An MCP server on the Jetson wraps Moonraker and the laser job: `machine_status`, `home`, `run_step` (drill, etch,
via fill, cure, mask cure, mask open, legend, paste, place, reflow), `camera_snapshot`, `pause`, `abort`. A person
approves the steps that need hands (the flip, the mask coat, loading parts). The agent can never override the
interlocks.

## Open questions for the EE

1. The galvo driver's supply voltage and the JPT source's 24 V current (from the units' manuals).
2. The KSD301 trip temperature.
3. Solder-paste dispenser: auger or pneumatic.
4. One 24 V PSU or two (laser on its own).
