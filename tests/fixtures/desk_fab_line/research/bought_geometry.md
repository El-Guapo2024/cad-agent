# Bought-part geometry survey (2026-09-13, haiku agent, web)

What real geometry exists for the box B parts. Dimensions here were read off a
page, not recalled. Anything absent must go through the MEASURED route with a
SOURCE, or be measured with callipers once the part is in hand.

| Part | Geometry found | STEP? | Source |
|---|---|---|---|
| SK-Cube CoreXY | 41 individual printed-part STEPs, no frame assembly | partial | github.com/SecKit/SK-Cube |
| Voron 0 | full master assembly, 32 MB zip, branch Voron0.2r1 | yes | github.com/VoronDesign/Voron-0 |
| NEMA 8 hollow shaft | 20x20 body, 27/30 mm long, 5 mm OD / 3 mm bore, 18 mNm | no | nanotec.com, omc-stepperonline.com |
| Juki 503/504/505 | tip sizes only: 1.0/0.6, 1.5/0.9, 3.5/1.7 mm. No length or shank | no | avipre.com Juki nozzle catalogue rev C3 |
| AR0234 camera | board 38x38 mm, 1/2.6", 1920x1200, 90-120 fps, M12 variants | no | arducam.com datasheet B0495 |
| 858D handpiece | main unit 150x100x138, lead 120 cm. Barrel dia and length NOT published | no | manualslib, CO-Z manual |
| Diaphragm pump | compact ~85x62x25 mm 239 g; ports and mounts vary by vendor | no | robotdigg, bodenpump |
| MGN12 / MGN15 | full HIWIN dimension tables. MGN12 12 mm wide 20 mm pitch; MGN15 15 mm, 25 mm | tables | HIWIN MG series catalogue 2023 |

## Not findable, must be measured in hand

Juki nozzle total length and shank diameter. AR0234 mounting hole pattern.
858D barrel diameter, total length, nozzle size, cable exit. Vacuum pump port
diameter and mounting holes.

## Gantry decision is open

SK-Cube ships printed-part STEPs but no frame assembly, so its envelope would
have to be measured. Voron 0 has a complete open assembly but is a 120 mm
build volume, smaller than the ~200 mm the cell wants. Neither is a clean fit.
Third option: design the gantry ourselves from MGN rails, whose dimensions are
fully published and standardised, which is the only one of the three where
every number is documented.

## Proven

`skcube_nema8_bracket` imported from the SK-Cube repository: 48.4 x 32.5 x
22.0 mm, 9.46 cm3, 0.45 s to import and measure. Note its origin sits at
(-270.8, -541.0, 171.5): a STEP carries the donor assembly's coordinates, so
an assembly must re-origin bought geometry rather than assume it is centred.
