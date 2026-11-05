"""pcb_blank: double-sided copper-clad laminate, Isola 370HR, 229 x 305 x 1.6 (the quarter panel CircuitJet IV takes)

Bought part. A lead-free-reflow laminate: Tg 180 C, Td 340 C, and 60 minutes at 260 C (T260, TMA) before it
delaminates, which is what lets it sit on the 240 C platen for the via cure (160 C, 30 min) and the reflow. The
copper (35 um a side) is part of the 1.6.
"""
from build123d import Box

SOURCE = "Isola 370HR data sheet: Tg 180 C (DSC), Td 340 C, T260 60 min, T288 30 min: https://www.isola-group.com/wp-content/uploads/data-sheets/370hr.pdf ; the 229 x 305 panel is CircuitJet IV's board size"
VENDOR = "Isola"
VERIFIED = True
MAX_TEMP_C = 260.0
MAX_TEMP_SOURCE = "Isola 370HR data sheet: T260 (time to delamination at 260 C, TMA) 60 minutes: https://www.isola-group.com/wp-content/uploads/data-sheets/370hr.pdf"
MASS_G = 207.0
MASS_SOURCE = "229 x 305 x 1.6 mm = 111.8 cm3 x 1.85 g/cm3 (fr4, cad tables materials); the copper is not counted apart"

PARAMS = {"size_x": 229.0, "size_y": 305.0, "thick": 1.6}


def build(size_x, size_y, thick):
    return Box(size_x, size_y, thick)
