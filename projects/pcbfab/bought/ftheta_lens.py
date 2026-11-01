"""ftheta_lens: Spectral Products

Bought part. The geometry below is an envelope for clearance checking, not a
model of the part: what the gates need to know is the space it occupies and
where it bolts down, and inventing detail beyond that only creates numbers
nobody checked.
"""
from build123d import Box, Cylinder, Pos

SOURCE = 'F-theta lens EFL 160 mm, 1064 nm, field 106 x 106, spot 26 um, WD 175.72 mm, length 52.26 mm, OD 89 mm, 0.5 kg, M85x1: Spectral Products F-Theta Lens Catalog https://optics.spectralproducts.com/PDF/F-ThetaLensCatalog.pdf'
VENDOR = 'Spectral Products'
VERIFIED = False

PARAMS = {'length': 89.0, 'width': 89.0, 'height': 52.26}


def build(length, width, height):
    body = Box(length, width, height)

    return body
