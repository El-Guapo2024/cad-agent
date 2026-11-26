"""The stencil: 0.125 mm mylar (polyester) sheet, its paste apertures and two 4.0 pin holes cut by the UV laser in
one job, so the holes register the apertures to the carrier's pins. Taped under the stencil frame.
Frame: its bottom at z 0, the carrier's front edge at y 0, centred in x.
"""
from build123d import Box, Cylinder, Pos

SOURCE = "0.125 mm (5 mil) mylar sheet, laser-cut in house"
VENDOR = None
VERIFIED = False
MATERIAL = "petg"         # mylar is PET; PETG is the nearest in the materials table

PARAMS = {"size_x": 190.0, "size_y": 170.0, "y0": 0.0, "thick": 0.125, "pin_x": 70.0, "pin_edge": 7.62, "hole": 4.05}


def build(size_x, size_y, y0, thick, pin_x, pin_edge, hole):
    f = Pos(0, y0 + size_y / 2.0, thick / 2.0) * Box(size_x, size_y, thick)
    for sx in (-1, 1):
        f -= Pos(sx * pin_x, pin_edge, thick / 2.0) * Cylinder(hole / 2.0, thick + 2)
    return f
