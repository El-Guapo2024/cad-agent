"""uv_source: JPT

Bought part. The geometry below is an envelope for clearance checking, not a
model of the part: what the gates need to know is the space it occupies and
where it bolts down, and inventing detail beyond that only creates numbers
nobody checked.
"""
from build123d import Box, Cylinder, Pos

SOURCE = "JPT Lark-355-5A 5 W 355 nm DPSS UV laser, air cooled (no chiller), head 348.5 x 144.6 x 126.2 mm without expander, about 6.5 kg, 10x beam expander built in, 0.7 mm beam at the output window, built-in PSU: https://haotianlasers.com/product/uv-laser-marking-machine-5w/ ; JPT's own page gives 272.5-307.5 x 144.6 x 121-125 by variant: https://en.jptoe.com/products/lasers/dpss-lasers/lark-355-3-5"
VENDOR = 'JPT'
VERIFIED = False

PARAMS = {'length': 348.5, 'width': 144.6, 'height': 126.2}


def build(length, width, height):
    body = Box(length, width, height)

    return body
