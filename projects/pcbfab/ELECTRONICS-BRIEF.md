# Desktop PCB fab: electronics brief (for the EE design), 2026-11-03

This replaces the 2026-11-01 brief. The machine was redesigned to do everything CircuitJet IV does: the board now
lives in one fixture for the whole job (a flip frame on an XY stage), the laser bridge focuses, and the head carries
dispensers and jets. New and changed loads are marked **new**.

## The machine now

One bench machine (about 1190 x 1070 x 880 mm with the extractor beside it), on Opulo's LumenPnP v4.2.0 with its
Y axis 300 mm longer. The CAD is on branch `pcbfab-demo` of El-Guapo2024/cad-agent:

- `projects/pcbfab`: the cabinet (4040 base; the electronics stand on four plates in it), the enclosure, the UV
  lamps, the extractor.
- `projects/fab_stage`: the fixture. The 229 x 305 board sits in a stainless flip frame. Under it is a heated vacuum
  platen (Tempco mica heater) that drops 135 mm so the frame can turn over. All of it rides an XY ball-screw stage
  that stitches the laser's 100 mm field and brings each part of the board under the head.
- `projects/laser_bridge`: the JPT Lark UV laser, SG7110 galvo and Jenoptik lens on a bridge. The bridge rides
  20 mm up and down on its posts to focus.
- `projects/head_tools`: on LumenPnP's head, beside its nozzles: two paste dispensers and two jets, each on its own
  SMC MXH10 air slide (16 mm), and a fixed height sensor.

Process (CircuitJet's order):
1. Drill, with the laser.
2. Fill the vias: the via-paste pen dots each hole while the platen's vacuum pulls the paste through. Cure on the
   platen (160 C), flip automatically, repeat on the other side.
3. Etch, with the laser.
4. Jet the solder mask, then UV-cure it with the gantry's lamps. The laser opens the pads and marks the legend
   (or the second jet prints a white legend).
5. Jet the gold finish (PV Nano Cell's inkjet gold ink) onto the opened pads and sinter it, on the platen or by
   the laser.
6. Flip. Dispense solder paste, place the parts, reflow on the platen.

The camera finds the board's fiducials after every flip. The height sensor sets the focus.

## Architecture

- **Host:** NVIDIA Jetson Orin Nano Developer Kit (100 x 79 x 21). It runs:
  - Klipper + Moonraker;
  - the cameras and AOI (board inspection; a JEPA-style model trained on good boards is the plan, after the
    hardware runs);
  - the laser job;
  - the MCP server the agent uses.
- **Motion MCU:** BIGTREETECH Octopus Pro (160 x 100, 8 driver slots). One may not be enough, see the stepper
  count below: add a second Klipper MCU (another Octopus, or an EBB-style CAN board on the head).
- **Galvo and laser controller:** JCZ LMCV4-Digit-M (5 V), USB to the Jetson. It drives the SG7110 (XY2-100) and
  the Lark's control port.

## Steppers (all NEMA 17 unless noted)

| Axis | Count | Where | Notes |
|---|---|---|---|
| LumenPnP X, Y, nozzle Z/rotation | Opulo's BOM | gantry | as Opulo specifies |
| **Stage X** | 1 | fab_stage | SFU1204 ball screw, 130 mm |
| **Stage Y** | 1 | fab_stage | SFU1204 ball screw, 205 mm |
| **Platen lift** | 2 (34 mm body) | fab_stage, one per post | Tr8x2 (self-locking), 135 mm. The two run together |
| **Flip** | 1 (34 mm) | fab_stage | GT2 belt 20T to 40T, half a turn. Needs a home (index) sensor |
| **Bridge focus Z** | 2 (34 mm) | laser_bridge, one per post | Tr8x2 (self-locking: the bridge must not run down unpowered), 20 mm. Klipper's z_tilt-style pair |

Each new axis needs an endstop: 6 axes (lift x2 and Z x2 can share as pairs). The flip needs an index at 0 and 180.

## Loads and sensors

| Subsystem | Part | Electrical |
|---|---|---|
| UV laser | JPT Lark-355-5A, 5 W 355 nm | **12 V DC, under 200 W** (JPT's table; the old brief said mains, which was wrong). Supply: Mean Well LRS-350-12. Enable, gate, frequency and alarm from the JCZ card |
| Galvo | SG7110, UV mirrors | Driver supply per the unit (commonly +/-15 V; check) |
| **Platen heater** | Tempco MSH00072 mica heater, 177.8 x 292.1, **625 W at 120 V** (was a 500 W Misumi). Cap 240 C | Omron G3NA-210B SSR on a Y92B-N50 heatsink. RS PRO PT1000 in the platen's slot, read by an Adafruit MAX31865 (3648). Selco ORA-500-QC cut-out (opens 249-271 C, rated 260 C max) on the platen's side, in series with the heater |
| Vacuum (via fill, hold-down) | SainSmart 24 V pump (42 W) + **SMC VT307V-5G1-01** 3-port valve (24 V DC, 4 W) | Pump switched; the valve vents the platen to let the board go |
| UV mask cure | 3 x LedWV 100 W 395 nm on the gantry | 48 V 3 A each. Supply: Mean Well LRS-600-48. Enable/PWM, lamp fans, cable along the X chain. Off unless the doors are shut |
| **Paste dispensers** | 2 x ViscoTec eco-PEN300 (solder paste; via paste) | Each needs ViscoTec's controller (stepper-driven progressive cavity) plus a pressure feed (0-6 bar) to the cartridge |
| **Tool slides** | 4 x SMC MXH10-20 air slides, one per dispenser and jet | Each needs a 24 V 5/2 solenoid valve (4 in all) and a reed switch for down/up; air at 0.3-0.7 MPa |
| **Jets** | 2 x Nordson EFD PICO Pulse (mask ink; gold finish ink or white legend ink) | Each needs a PICO Touch controller and air/fluid pressure. Trigger from the MCU |
| **Height sensor** | Panasonic HG-C1030 (30 +/- 5 mm, 10 um) | 24 V DC, 40 mA; analogue or IO-Link output to the MCU or Jetson |
| Pick-and-place | LumenPnP's nozzles, vacuum, cameras | As Opulo's design |
| Cameras / AOI | LumenPnP's top and bottom cameras | USB to the Jetson |
| **Fume extraction** | BOFA V250 (HEPA 99.997 % at 0.3 um + 2 kg carbon, 180 m3/h) | **115 V, 135 W**, beside the machine, 50 mm hose to the back. Run it whenever the laser, the lamps, the jets or the reflow run (BOFA has a remote start input; check) |
| Enclosure | 2 x Omron D4NS door switches, key switch (Schneider XB5AG21), e-stop (XB5AS8442) | Part of the laser and UV interlock |
| Mains entry | Schurter KM00.1105.11 (C14, fused, 2-pole switch) | In the back's lower-right panel |

## Safety (hardware, not software)

- The 5 W UV laser is Class 4. The two door switches, the key switch and the e-stop run through an Omron G9SE-201
  safety relay, which cuts the laser's enable and the UV lamps' supply. The MCU only reads the state.
- The window is OptoSigma YL-510C-Y2(5), OD 8 at 355 nm, in the upper-left front panel.
- The heater's cut-out is independent of the controller.
- Mains (heater, PSUs, extractor) is fused, earthed and kept apart from low voltage.

## Power (estimate, for the EE to size)

| Rail | Loads | Supply |
|---|---|---|
| Mains 120 V | heater 625 W via SSR; PSUs; extractor 135 W | |
| 24 V | all steppers, pump 42 W, valve, fans, dispenser controllers, height sensor | Mean Well LRS-350-24 (14.6 A). Check the stepper count against it; an LRS-600-24 may be needed |
| 48 V | UV lamps, 9 A | Mean Well LRS-600-48 |
| 12 V | Lark source, under 200 W | Mean Well LRS-350-12 |
| 5 V | JCZ card | |
| Jetson | its own supply | |

The cabinet's plates hold all of these in 109 mm of height (`projects/pcbfab/assembly.py` has the layout).

## Agent interface

An MCP server on the Jetson wraps Moonraker and the laser job, with these tools:
- `machine_status`, `home`, `camera_snapshot`, `pause`, `abort`;
- `run_step`, for each step: drill, via fill, cure, flip, etch, mask, mask cure, mask open, legend, gold finish, paste,
  place, reflow, inspect.

A person approves loading the board and the parts. The agent can never override the interlocks.

## Open questions for the EE

1. The galvo driver's supply voltage, and the Lark's control pinout (from the units' manuals).
2. ViscoTec and PICO controllers: their interfaces to Klipper, and the air supply (a small compressor in the
   cabinet, or shop air).
3. One motion board or two, for 7 new steppers plus LumenPnP's, and 4 slide valves.
6. Compressed air: the slides, the jets and the pens' feeds all need it. A small oil-free compressor with a tank
   in the cabinet, or shop air with a regulator and filter.
4. The height sensor's output (analogue or IO-Link) and where it is read.
5. The gold finish ink (PV Nano Cell Sicrys IAu20W): its sintering profile is not published (commercial gold inks
   cure above about 190 C). It cures on the platen at 200 to 240 C if the profile fits; otherwise the laser
   sinters it, and the laser job needs that step.
