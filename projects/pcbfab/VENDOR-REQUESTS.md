# Vendor requests that close the design's open rows (drafts, not sent)

Each request closes rows that keep `cad done` from passing (UNCHECKED provenance, mass or heat) or the one open
process question. Send from BraneBoard's own address.

## 1. PV Nano Cell: the gold finish ink (closes CircuitJet's last step)

> Subject: Sicrys IAu20W gold ink, sintering profile and solderability data
>
> We are building a desktop PCB fabrication machine. We want to jet your Sicrys IAu20W gold ink onto copper pads
> as a solderable finish (with a Nordson PICO Pulse jet valve), then cure it on a hot plate capped at 240 C. Could
> you send:
> - the technical data sheet, with the recommended sintering profile (temperature and time);
> - whether it sinters at or below 240 C, and its sheet resistance after that;
> - any solderability or wetting data with SnBi or SAC solders;
> - its viscosity and surface tension at jetting temperature;
> - sample availability and price.

## 2. JPT Opto-electronics: the Lark-355-5A (laser)

> Subject: Lark-355-5A STEP model, mass and control pinout
>
> Could you send the Lark-355-5A's STEP model and outline drawing (mounting holes, beam exit height and position),
> its mass, its supply requirement (12 V DC, peak current), and the control connector's pinout (enable, gate,
> frequency, alarm)?

## 3. Sino-Galvo (or the reseller): SG7110 galvo

> Subject: SG7110 (355 nm mirrors) STEP model, mass and driver supply
>
> Could you send the SG7110's STEP model or outline drawing (the M85 output thread's position, the input aperture's
> height), its mass, and the driver's supply voltage and current?

## 4. SMC: MXH10-20 slide

> Subject: MXH10-20Z CAD model
>
> Could you send the STEP model of the MXH10-20Z compact slide (or the dimension drawing with H, W, L and the table's
> mounting holes)?

## 5. Nordson EFD: PICO Pulse jet valve

> Subject: PICO Pulse jet valve drawing and controller interface
>
> Could you send the jet valve's dimension drawing or STEP (mounting holes, nozzle position) and the PICO Touch
> controller's trigger input specification?

## 6. Parts to weigh or ask for (the mass rows)

These publish no mass:
- Sorotec SFU1204 ball screws and nuts, BK10
- Oriental Motor MCL200508 couplings
- Tr8x2 screws and nuts
- Tempco MSH00072 heater
- RS PRO PT1000
- Selco ORA-500-QC
- LedWV 395 nm lamp
- SainSmart pump
- Jetson Orin Nano dev kit
- BTT Octopus Pro
- JCZ LMCV4
- Mean Well LRS-350-12

Weigh each on arrival, or ask the vendor. LumenPnP's frame and gantry have no mass either: Opulo's BOM lists the
parts, so weigh a built LumenPnP or sum the BOM.

## 7. Parts to measure on arrival (the provenance rows)

Measure these and set `VERIFIED = True` in each one's file, with the reading as its source:
- Lark (the vendor's 307.5 x 144.6 x 121.2 against a reseller's 348.5)
- SG7110
- PICO jet
- MXH10 slide height
- HG-C1030
- Tempco heater thickness
- Tr8x2 nut
- LRS-350-12 case
- Octopus Pro height
- LMCV4 board
- PT1000 (RS part number)
- Selco ORA-500-QC body and bracket
