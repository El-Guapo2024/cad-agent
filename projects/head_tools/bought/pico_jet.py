"""pico_jet: Nordson EFD PICO Pulse jet valve, 22 W x 75 L x 120 H, M4 mounting

Bought part, an envelope: its nozzle at z = 0 (the bottom), 75 deep along y from its mounting face (y = 0) forward
(-y). Jets the UV solder mask and the legend ink as dots (0.5 nl minimum, 1000 Hz continuous), 1.5 mm over the board.
"""
from build123d import Box, Pos

SOURCE = "Nordson EFD PICO Pulse data sheet: 22 W x 120 H x 75 L mm, 362 g without cable, 35 bar, M4x0.7 mounting, 0.5 nl, 1000 Hz: https://assets.testequity.com/te1/Documents/pdf/nordson/Nordson-EFD_Pico-Pulse-Contact-Dispense-Valve_DataSheet_0624.pdf (the contact-valve sheet; the jet's own sheet gives the same body per a search excerpt)"
VENDOR = "Nordson EFD"
VERIFIED = False
MASS_G = 362.0
MASS_SOURCE = "Nordson EFD PICO Pulse data sheet: 362 g without cable"

PARAMS = {"width": 22.0, "length": 75.0, "height": 120.0}


def build(width, length, height):
    return Pos(0, -length / 2.0, height / 2.0) * Box(width, length, height)
