"""galvo: Sino-Galvo

Bought part. The geometry below is an envelope for clearance checking, not a
model of the part: what the gates need to know is the space it occupies and
where it bolts down, and inventing detail beyond that only creates numbers
nobody checked.
"""
from build123d import Box, Cylinder, Pos

SOURCE = 'SG7110 10 mm aperture galvo head, body 118.5 x 96.5 x 93.6 mm per vendor listing https://bestsuppliers.com/products/5rf2i14leee2/free-shipping-1064nm-fiber-laser-scanning-galvo-head-rc7110-sg7110-red-pointer-0100w-input-aperture (other listings: 114-118 x 96.5 x 93.7)'
VENDOR = 'Sino-Galvo'
VERIFIED = False

PARAMS = {'length': 118.5, 'width': 96.5, 'height': 93.6}


def build(length, width, height):
    body = Box(length, width, height)

    return body
