"""fiber_source: JPT

Bought part. The geometry below is an envelope for clearance checking, not a
model of the part: what the gates need to know is the space it occupies and
where it bolts down, and inventing detail beyond that only creates numbers
nobody checked.
"""
from build123d import Box, Cylinder, Pos

SOURCE = 'JPT YDFLP-E-20-M7-S-R 20 W MOPA, 2-500 ns, module about 245 x 200 x 65 mm, 3.75 kg net, per the JPT user manual V1.4 https://cdn.shopify.com/s/files/1/2222/7859/files/YDFLP-E-20-30-M7-S-R_User_Manual_V1.4EN_2021_6384987b-ce7b-43c3-84e4-50109dac396f.pdf (read through a search summary: re-check on the manual); sold by Cloudray at USD 2,549'
VENDOR = 'JPT'
VERIFIED = False

PARAMS = {'length': 245.0, 'width': 200.0, 'height': 65.0}


def build(length, width, height):
    body = Box(length, width, height)

    return body
