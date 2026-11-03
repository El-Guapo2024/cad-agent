"""slide: SMC MXH10-20 compact slide (air slide table), 10 mm bore, 20 mm stroke: one per dispenser and jet

Bought part, an envelope: W 19 (x) x H 23 (y) x L 66.5 (z, along its stroke), its mounting face (the body's back)
at y = 0 and the table's face at y = -23. Each tool rides its own, so only the working tool comes down (with one
lift for all four, a neighbour came down onto the flip frame's edge bar). The fab needs air for the jets and the
pens anyway. Read from SMC's MXH catalogue (a text extraction of its tables): mass 148 g at 20 stroke, 39.3 N out
and 33.0 N in at 0.5 MPa, the phi 10 drawing's 19 wide and L 46.5 + stroke; the 23 height is read from that drawing's
dimension list and is UNVERIFIED (SMC's product page gives H 47 for the 25 stroke, which may be the table's length).
"""
from build123d import Box, Pos

SOURCE = "SMC MXH series catalogue (MXH10: mass 148 g at 20 mm stroke; theoretical output 39.3 N OUT / 33.0 N IN at 0.5 MPa; phi 10 dimensions W 19, L 46.5 + stroke): https://automationdistribution.com/content/files/pdf/mxh.pdf ; product page https://elasticsearch.smcpneumatics.com/25A-MXH10-25Z.html"
VENDOR = "SMC"
VERIFIED = False
MASS_G = 148.0
MASS_SOURCE = "SMC MXH catalogue, mass table: MXH10, 20 mm stroke, 148 g"

PARAMS = {"width": 19.0, "height": 23.0, "length": 66.5}


def build(width, height, length):
    return Pos(0, -height / 2.0, 0) * Box(width, height, length)
