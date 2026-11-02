"""uv_source: JPT

Bought part. The geometry below is an envelope for clearance checking, not a
model of the part: what the gates need to know is the space it occupies and
where it bolts down, and inventing detail beyond that only creates numbers
nobody checked.
"""
from build123d import Box, Cylinder, Pos

SOURCE = "JPT Lark-355-5A 5 W 355 nm DPSS UV laser, air cooled, 12 V DC, <200 W, 307.5 x 144.6 x 121.2 mm (L x W x H), 6.5 kg, beam 0.5 mm: JPT's own spec table https://en.jptoe.com/products/lasers/dpss-lasers/lark-355-3-5 (a reseller lists 348.5 x 144.6 x 126.2 'without expander': https://haotianlasers.com/product/uv-laser-marking-machine-5w/)"
VENDOR = 'JPT'
VERIFIED = False
MASS_G = 6500.0
MASS_SOURCE = "JPT's Lark-355 spec table (in SOURCE): 6.5 kg"

PARAMS = {'length': 307.5, 'width': 144.6, 'height': 121.2}


def build(length, width, height):
    body = Box(length, width, height)

    return body
