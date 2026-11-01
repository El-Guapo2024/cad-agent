"""vacuum_pump: SainSmart

Bought part. The geometry below is an envelope for clearance checking, not a
model of the part: what the gates need to know is the space it occupies and
where it bolts down, and inventing detail beyond that only creates numbers
nobody checked.
"""
from build123d import Box, Cylinder, Pos

SOURCE = 'SainSmart vacuum pump for CNC aluminium vacuum tables: 24 V, -85 kPa, 42 W, 40 L/min, 100 x 41 x 98 mm, needs a 24 V 2 A supply https://sainsmart.com/products/vaccum-pump-for-cnc-aluminum-vacuum-table'
VENDOR = 'SainSmart'
VERIFIED = False

PARAMS = {'length': 100.0, 'width': 41.0, 'height': 98.0}


def build(length, width, height):
    body = Box(length, width, height)

    return body
