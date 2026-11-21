"""Hex drive shaft, 10 mm across flats, steel: runs across both rails and turns both belts' drive pulleys, so the rear
rail stays driven wherever it is (its pulley slides along). Axis along y, centred.

DIMENSIONS ARE UNVERIFIED: 10 mm hex bar is a stock size; pick the supplier.
"""
from build123d import RegularPolygon, extrude, Plane

SOURCE = "stock 10 mm A/F hex bar; length to the design"
VENDOR = None
VERIFIED = False

PARAMS = {"length": 420.0, "af": 10.0}


def build(length, af):
    return extrude(Plane.XZ.offset(-length / 2.0) * RegularPolygon(af / 2.0, 6, major_radius=False), length)
