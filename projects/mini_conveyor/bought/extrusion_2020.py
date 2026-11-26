"""20 x 20 aluminium T-slot extrusion, cut to length: the module's cross beams and legs. Envelope with the centre
bore; slots not modelled. Axis along z, centred.
"""
from build123d import Box, Cylinder

SOURCE = "cad tables extrusions: 2020 (w 20, h 20, slot 6, bore 4.2); length cut to order"
VENDOR = None
VERIFIED = True

PARAMS = {"length": 100.0, "w": 20.0, "bore": 4.2}


def build(length, w, bore):
    return Box(w, w, length) - Cylinder(bore / 2.0, length + 2)
