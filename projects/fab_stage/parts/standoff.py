"""Standoff: a stainless spacer between the carrier and the heater's clamp plate, an air gap under the heater.

8 mm round, M3 through.
"""
from build123d import Cylinder

MATERIAL = "stainless"
PROCESS = "cnc"
MIN_FEATURE_MM = 1.0

PARAMS = {"dia": 8.0, "height": 10.0, "hole": 3.4}


def build(dia, height, hole):
    return Cylinder(dia / 2.0, height) - Cylinder(hole / 2.0, height + 2)
