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
