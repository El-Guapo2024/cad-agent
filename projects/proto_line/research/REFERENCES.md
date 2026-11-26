# Bare-bones 2-layer prototype line: whose ideas, and the weekend list (2026-11-26)

## Taken from others
| Station | Idea | From |
|---|---|---|
| Pick and place | LumenPnP, open source; scriptable from Python (leash); paste toolhead | https://cdn.shopify.com/s/files/1/0570/4256/7355/files/LumenPnP-v3.1-brochure.pdf |
| PnP software | OpenPnP (fiducials, feeders, paste dispensing) | https://github.com/openpnp/openpnp |
| Paste, stencil-less | Paste dispensed by the PnP ahead of placing | https://www.hackster.io/news/erich-styger-upgrades-his-openpnp-pick-and-place-machine-to-dispense-solder-paste-510cab133a70 |
| Paste, stencil | Stencil jig (GPL-3.0), board flush, foil on pins | https://github.com/makermoekoe/stencil-jig |
| Paste dispenser | Open automatic paste dispenser | https://github.com/makanddream/automatic-solder-paste-dispenser |
| Reflow | Toaster oven + open controller (Reflowduino) | https://hackaday.io/project/27900-reflowduino-bluetooth-reflow-oven-controller/details |
| Reflow | Open oven with a browser temperature graph | https://www.github.com/minor-industries/reflow-oven |
| AI-aided CAD | build123d over MCP (what cad-agent already does, with checks) | https://github.com/pzfreo/build123d-mcp |

No open-source inline (conveyor) reflow oven or automatic stencil printer was found; those stay hand steps for v1.

## Weekend list
Make:
- carrier (aluminium, CNC), one per board in flight
- nest (aluminium, CNC), one per station: laser, paste, LumenPnP
- stencil frame (PETG, printed)
- laser riser: waits on the laser's lens working distance

Buy:
- 4 mm dowel 4m6x20 and 4 mm diamond locating pin per nest; 3 mm dowels 3m6x6 (2 per carrier)
- 0.125 mm mylar sheet; FR4 1.6 double-sided blanks 150 x 150
- toaster oven, thermocouple + SSR controller; wire rack
- via rivets or conductive paste; solder paste; squeegee

## One machine for all three stages: who has done it (searched 2026-11-26)
| Example | What it combines | Note |
|---|---|---|
| BotFactory SV2 | conductive-ink printing, paste, pick and place, reflow bed in one | the closest commercial match; 0603 and 0.4 mm pitch; board stays put, tools come to it. https://eejournal.com/article/botfactory-all-in-one-pcb-printing-and-assembly , https://industrytoday.com/botfactory-sv2-3d-pcb-printer-pick-and-place-machine |
| Voltera V-One | printing, paste, reflow on a heated bed; placing by hand | https://makezine.com/article/technology/microcontrollers/voltera-v-one-makes-custom-pcbs-home-less-mess/ |
| LPKF line | ProtoLaser, ProtoPrint, ProtoPlace, ProtoFlow: our steps, as four machines | https://www.lpkf.com/en/industries-technologies/research-in-house-pcb-prototyping/process-steps-for-pcb-prototyping |
| Jubilee (open), E3D ToolChanger | one gantry, swapped tools: lasers, paste, pick and place named as tools | https://github.com/machineagency/jubilee , https://e3d-online.com/blogs/news/research-and-development-motion-system-and-tool-changer |
| OpenPnP hot air from the toolhead | reflow in the PnP machine | https://www.hackster.io/news/erich-styger-upgrades-his-openpnp-pick-and-place-machine-to-dispense-solder-paste-510cab133a70 |
| SMD Reflow Hotplate (open) | a hot plate a bed could be built from | https://hackaday.io/project/185935-smd-reflow-hotplate/log/208228-schematic-overview |

Laser on PCB: UV ablates copper with little charring; ablating all the copper chars FR4, so take ~90% and etch or
accept it; drilling FR4 is the hard part; FR4 fumes are toxic.
https://www.pcbway.com/blog/Engineering_Technical/Printed_circuit_board_processing_with_UV_lasers.html ,
https://hackaday.com/2023/07/17/diy-laser-for-ablating-metal , https://hackaday.com/2025/01/05/perfecting-20-minute-pcbs-with-laser ,
https://www.instructables.com/Double-sided-PCBs-with-a-laser-cutter

## Old SMT machine plans
- MDC ECM97: scanned A3 mechanical drawings (X and Y axes, servo assembly, feeder rack, nozzle holder, heads,
  pneumatics, PCB conveyor), install guide, manual. https://philpem.me.uk/elec/ecm97/start
- Juki/Zevatech 710 manual, maintenance checklist and spare parts list. https://groups.google.com/g/openpnp/c/fdkcT3Yafuk
- Siemens Siplace S-27 HM service manual. https://www.mikrocontroller.net/attachment/701937/siplace-s27hm.pdf
- Georgia Tech GTRI PPMachine manual (too large to read here). https://cshaft.gtri.gatech.edu/files/2020/08/PPMachine-Manual.pdf
- Quad QSA-30A retrofit notes. https://pico-systems.com/QSA30.html
- MIT CBA APS Gold-Place L40. https://fab.cba.mit.edu/content/tools/APS_L40_Pick_and_Place/index.html
