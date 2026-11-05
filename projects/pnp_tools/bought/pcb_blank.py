"""pcb_blank: double-sided copper-clad FR4, 150 x 150 x 1.6, 1 oz (35 um) a side (Juan, 2026-11-05)

Bought part. Juan chose 150 x 150 boards so the UV marker's 150 mm lens covers a whole board with no stage. Cut four
from one 12 x 12 in MG Chemicals 555 sheet (305 x 305: two 150 boards a side, 5 mm left for the cuts). MG does not
list its Tg, so no temperature rating is claimed here; the copper is part of the 1.6.
"""
from build123d import Box

SOURCE = "MG Chemicals 555, 12 x 12 in, 0.062 in, 1 oz double-sided FR4 (DigiKey 473-1007-ND): https://www.digikey.com/en/products/detail/mg-chemicals/555/559707 ; 150 x 150 is Juan's board size"
VENDOR = "MG Chemicals"
PART_NUMBER = "555"
VERIFIED = True
MASS_G = 66.6
MASS_SOURCE = "150 x 150 x 1.6 mm = 36.0 cm3 x 1.85 g/cm3 (fr4, cad tables materials); the copper is not counted apart"

PARAMS = {"size_x": 150.0, "size_y": 150.0, "thick": 1.6}


def build(size_x, size_y, thick):
    return Box(size_x, size_y, thick)
