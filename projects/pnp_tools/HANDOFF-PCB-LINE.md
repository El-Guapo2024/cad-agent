# PCB line: handoff (2026-11-05)

Juan's goal: a desktop PCB line that does what CircuitJet does (drill, via fill, etch, solder mask, finish, legend,
paste, place, reflow), bought and retrofitted, every machine driven by an LLM (one MCP server per machine).

Repo: El-Guapo2024/cad-agent, branch `pcbfab-demo` (worktree `~/work/pcbfab-wt`). Nothing is merged to main; Juan must
OK the merge. Run cad with `CAD_PROJECTS=$PWD/projects CAD_WARM=0 PYTHONPATH=$PWD PATH=~/work/cad-agent/.venv/bin:$PATH bin/cad ...`
from the worktree (options before positionals in `lib use`). Don't force-push (denied); don't touch `~/work/cad-agent`.

## Decisions Juan made

| Machine | Decision |
|---|---|
| Laser | 5 W 355 nm UV galvo with a JCZ (EZCad) board, so LightBurn / MeerK40t can drive it. Boards are **150 x 150 mm**: the lens covers a whole board, no stage, the board sits on pins under the lens. Current pick: Amazon B0DFCLQZ5H ($2,438, US stock, Sino-Galvo, EzCad lite + LightBurn, water cooled, 200 mm lens, returnable to 2027-01-31; ask the seller the UV source brand). Cheaper eBay options found: CNCZONE US-stock $1,979 (ebay 397310861891), HL Laser CRS-355-5 $1,749 (ebay 206245619224). Not diode, not fiber, not xTool (closed). |
| Pick-and-place | **Self-built LumenPnP v4** from Opulo's open files: buy Opulo's control box + custom kits (toolhead x2, drag chain, harnesses, ring lights, endstops), generic motors/PSU/tubing, Opulo frame/rail/belt kits; Juan prints the plastic. Rejected: used Charmhigh CHMT36VA (~$3.1k delivered, one-way controller swap), new Opulo $1,995. |
| Head tools | The process tools ride the LumenPnP head on air slides: 4 syringe barrels with needles, each driven by a bench 983A pneumatic dispenser (solder paste, silver via paste, UV mask, legend), clone MXH10-20 slides, 4V110 24 V valves, a BLTouch for height, 3 AliExpress 395 nm UV LED lamps on the gantry for mask cure. Replaces ViscoTec eco-PEN, Nordson PICO and Panasonic HG-C1030. |
| Oven | **DIY** convection toaster oven (Black+Decker TO3250XSB) + Pico + MAX31855 + Inkbird SSR-40DA, scripted over USB serial; it also does the 160 C silver via cure (no hot plate). |
| Stencils | Manual stencil printer + squeegee; the UV laser cuts Kapton/Mylar stencils. |

## What exists

- `projects/pnp_tools/LINE-ORDER.csv`: the whole order list, about $5,955 priced (50 lines; `price_checked` = yes/partial/no; many marketplace prices are search snippets). Same list as a page with tick boxes: https://claude.ai/artifact/QtLdCMMcRQJkQYoxiv2snC (private to Juan). Nothing has been bought.
- `projects/lumenpnp_stock`: stock LumenPnP (frame + gantry bodies from Opulo's STEPs).
- `projects/pnp_tools`: LumenPnP + head tools + UV lamps + board fixture (150 x 150 board on a 3-pin aluminium plate). Last verify (commit c4f0839): **0 FAIL, UNCHECKED** on render approval, masses of `lumenpnp_stock/frame`, `gantry`, `uv_lamp`, and four datasheet-sourced sizes (height_sensor, pico_jet, slide, uv_lamp).
- `projects/lumenpnp_stock/mobo_bom_jlc_fixed.csv`: corrected JLC BOM for Opulo's motherboard (only if one is ever built at JLC; buying the $250 control box is cheaper).
- `projects/fab_stage`, `projects/pcbfab`: superseded by the 150 mm decision and the two-machine line. Leave them, or delete with Juan's OK.

## What is left

1. **Rebuild pnp_tools' head tools for the ordered parts.** Swap `bought/eco_pen.py` and `pico_jet.py` for a syringe barrel + needle (Nordson Optimum 30 cc: 115.9 mm long per Nordson's typical data; diameter and flange not published, so measure them), and `height_sensor.py` for a BLTouch. From Antclabs' official drawing (https://www.antclabs.com/bltouch-v3, SpecV31.jpg): holes 3.2 mm on 18.0 mm centres, 36.3 mm body, pin to 46.6 mm stowed, +6.6 mm deployed, 10 g. The body width isn't given, so measure it. Re-draw `pen_clamp` for the barrel, then update the spec's tool names and the mass row. Use measured or datasheet sizes only, never sizes from memory.
2. **UV lamps:** replace the LedWV envelope with the AliExpress 395 nm 100 W kit's real size once it arrives, and give it a mass.
3. **Masses for lumenpnp_stock frame and gantry:** make them bought parts with a mass and a source. A scale reading works.
4. **Laser station project:** a 3-pin fixture plate for the 150 x 150 board under the marker's lens, at the lens's working distance. It needs the marker's drawing, or its column height and focal distance, from the seller.
5. **Renders:** run `bin/cad render`, show them to Juan, and let him run `bin/cad approve`.
6. **Merge:** `cad verify` and `cad done` each project, then merge `pcbfab-demo` into main only with Juan's OK. The "rules changed" stop-hook note clears only after that merge.
7. **Electronics and LLM control** (not started):
   - an MCP server per machine: laser via LightBurn or MeerK40t on the JCZ board, PnP via OpenPnP or G-code to the LumenPnP Marlin board, oven via the Pico serial protocol;
   - the 983A triggers, valves and lamp SSRs on the LumenPnP control box's spare outputs or a small IO board.

## Before ordering (Juan)

- Ask the laser seller for the UV source brand (JPT, Huaray or Inno) and whether a 150 mm lens is available.
- Duties: US duty on Chinese goods runs 35-92.5% (per JLCMC's tariff page). Prefer US stock or DDP.
- The "partial" prices in the CSV are from search snippets (Amazon, eBay and AliExpress blocked the tools), so confirm each one at checkout.
- Watch for a used LumenPnP (about $1k, EEVblog buy/sell or eBay), a ProtoMat mill at GovDeals (about $275-1,000), and the BidSpotter "Digital Radar Manufacturing" surplus sale (San Jose, closes 2026-11-30).
