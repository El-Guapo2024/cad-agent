"""galvo_card: JCZ LMCV4-Digit-M EZCAD2 galvo and laser control card, USB to the Jetson, 5 V

Bought part, an envelope: its box, its base at z = 0.
"""
from build123d import Box, Pos

SOURCE = "JCZ LMCV4-Digit-M manual: 5 V DC, operating 25 +/- 10 C; its size is on a drawing image only, so 150 x 100 x 25 is RESERVED, not measured: https://cdn.shopify.com/s/files/1/2222/7859/files/f6fd0e92a8c2c657e046afba8aa67163_d71daf65-48a7-4054-bf23-b0486e3af2b9.pdf"
VENDOR = "JCZ"
VERIFIED = False

PARAMS = {"length": 150.0, "width": 100.0, "height": 25.0}


def build(length, width, height):
    return Pos(0, 0, height / 2.0) * Box(length, width, height)
