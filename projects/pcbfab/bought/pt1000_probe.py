"""pt1000_probe: RS PRO PT1000, 3 mm x 100 mm sheath, rated 400 C

Bought part. The hot plate's temperature sensor, read by an Adafruit MAX31865 (#3648); pushed 75 mm into a 3.2 mm
bore in the plate's edge, 25 mm standing out for its lead. Picked by the electronics lane (about USD 47); the RS
part number and drawing are not checked here. The geometry is the sheath only, an envelope.
"""
from build123d import Cylinder

SOURCE = "RS PRO PT1000 probe, 3 mm x 100 mm, rated 400 C, about USD 47: the electronics lane's pick (2026-11-01), RS part number to be confirmed"
VENDOR = "RS PRO"
VERIFIED = False
MAX_TEMP_C = 400.0
MAX_TEMP_SOURCE = "RS PRO PT1000 3 x 100 mm, rated 400 C, as the electronics lane quotes it (datasheet not read here)"

PARAMS = {"dia": 3.0, "length": 100.0}


def build(dia, length):
    return Cylinder(dia / 2.0, length)     # along z; the assembly lays it along x
