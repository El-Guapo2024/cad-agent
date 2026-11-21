"""40 x 40 aluminium T-slot extrusion, cut to length: the frame's legs and beams. Envelope with the centre bore.

The section is the repo's extrusion table's 4040 (cad tables extrusions); the slots are not modelled. Axis along z,
centred.
"""
from build123d import Box, Cylinder

SOURCE = "cad tables extrusions: 4040 (w 40, h 40, slot 8, bore 6.8); length cut to order"
VENDOR = None
VERIFIED = True

PARAMS = {"length": 400.0, "w": 40.0, "bore": 6.8}


def build(length, w, bore):
    return Box(w, w, length) - Cylinder(bore / 2.0, length + 2)
