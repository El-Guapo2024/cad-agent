"""Trapezoidal lead screw, Tr12 x 3, cut to length: two of them, belted together, move the rear rail. Axis along y.

DIMENSIONS ARE UNVERIFIED (nominal Tr12 only); pick the maker and check the journal ends.
"""
from build123d import Cylinder, Rot

SOURCE = "nominal Tr12 x 3 (ISO 2904 designation); length to the design"
VENDOR = None
VERIFIED = False

PARAMS = {"length": 420.0, "dia": 12.0}


def build(length, dia):
    return Rot(90, 0, 0) * Cylinder(dia / 2.0, length)
