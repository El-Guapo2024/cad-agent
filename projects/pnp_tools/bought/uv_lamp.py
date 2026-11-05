"""uv_lamp: LedWV

Bought part. The geometry below is an envelope for clearance checking, not a
model of the part: what the gates need to know is the space it occupies and
where it bolts down, and inventing detail beyond that only creates numbers
nobody checked.
"""
from build123d import Box, Cylinder, Pos

SOURCE = 'UV LED curing lamp 395 nm 100 W: product 110 x 20 x 118 mm, emitting area 72 x 8 mm, 12-16 W/cm2, 48 V 3 A, air-cooled https://www.ledwv.com/uv/uv-led-curing-lamp-source-395nm-100w-p-1199.html'
VENDOR = 'LedWV'
VERIFIED = False

PARAMS = {'length': 110.0, 'width': 20.0, 'height': 118.0}


def build(length, width, height):
    body = Box(length, width, height)

    return body
