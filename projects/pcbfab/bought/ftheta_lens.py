"""ftheta_lens: Wavelength Opto-Electronic

Bought part. The geometry below is an envelope for clearance checking, not a
model of the part: what the gates need to know is the space it occupies and
where it bolts down, and inventing detail beyond that only creates numbers
nobody checked.
"""
from build123d import Box, Cylinder, Pos

SOURCE = 'SL-355-110-160-D10-LP F-theta lens, 355 nm, EFL 160, 10 mm input beam, 110 x 110 field at +/-27.8 deg, working distance 213.35 mm, outer dia 103, total length 57, spot 13.2-42.4 um: https://www.wavelength-ir.com/355nm-laser-f-theta-scan-lens-product/'
VENDOR = 'Wavelength Opto-Electronic'
VERIFIED = False

PARAMS = {'length': 103.0, 'width': 103.0, 'height': 57.0}


def build(length, width, height):
    body = Box(length, width, height)

    return body
