"""camera: Raspberry Pi

Bought part. The geometry below is an envelope for clearance checking, not a
model of the part: what the gates need to know is the space it occupies and
where it bolts down, and inventing detail beyond that only creates numbers
nobody checked.
"""
from build123d import Box, Cylinder, Pos

SOURCE = 'Raspberry Pi High Quality Camera (IMX477): board 38 x 38 x 18.4 (Arducam listing, https://www.desertcart.lk/products/433359969) with the 6 mm CS lens, 30 dia x 34 (Waveshare table, https://www.waveshare.com/product/raspberry-pi-hq-camera.htm): the fiducial camera, looking down; 52.4 tall overall'
VENDOR = 'Raspberry Pi'
VERIFIED = False

PARAMS = {'length': 38.0, 'width': 38.0, 'height': 52.4}


def build(length, width, height):
    body = Box(length, width, height)

    return body
