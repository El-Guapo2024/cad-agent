"""eco_pen: ViscoTec preeflow eco-PEN300 volumetric (progressive cavity) dispenser, art. 20505

Bought part, an envelope: a 33 mm cylinder 216 long along z, its Luer-lock outlet at z = 0 (the bottom), the G1/8
material inlet at the top. 0.12 to 1.48 ml/min, smallest dose 1 ul: the fab's solder-paste and via-paste dispensers.
The needle (a 1/4 in Luer needle, 6.35 below the outlet) is not drawn.
"""
from build123d import Cylinder, Pos

SOURCE = "ViscoTec preeflow eco-PEN300 (art. 20505): L 216, dia 33, 280 g, 0-6 bar operating, 0.12-1.48 ml/min, 1 ul: https://unchainedrobotics.de/en/products/end-of-arm-effectors/end-of-arm-tools/dispensers/vieweg-volume-valve-preeflow-eco-pen450 (eco-PEN range page) and ViscoTec's product page"
VENDOR = "ViscoTec"
VERIFIED = True
MASS_G = 280.0
MASS_SOURCE = "ViscoTec eco-PEN300 data: 280 g"

PARAMS = {"dia": 33.0, "length": 216.0}


def build(dia, length):
    return Pos(0, 0, length / 2.0) * Cylinder(dia / 2.0, length)
