"""0.96 inch 128x64 OLED module (Winstar WEA012864D-03), as the envelope a panel has to clear.

Figures from Winstar's OLED SPECIFICATION WEA012864D-03 (General Specification and Contour Drawing,
pages 2-3):

    module           27.30 x 27.30 x 2.37 mm   PCB 1.0 mm thick, glass stack in front of it
    glass (panel)    26.70 +-0.2 x 19.26 +-0.2 mm, centred on the PCB (0.3 mm margin each side,
                     4.02 mm above and below)
    viewing area     23.94 x 12.06 mm          active area 21.74 x 10.86 mm (not modelled)
    mounting holes   4 x 2.5 mm plated, 20.7 x 23.2 mm apart, centred on the PCB
    header           4 pins, 2.54 pitch, on the back of the PCB: body 1.5 high, pins 6.0 beyond it
                     (7.5 +-0.5 from the PCB), centred in x, 1.65 mm from the top edge

Simplified: the PCB outline is a rectangle (the drawing has rounded corners and a notch under the
glass), the glass is one block, and the solder stubs on the front side of the PCB are left out. The pins
are 0.6 mm square, scaled from the drawing.

Glass 1.37 mm thick = 2.37 - 1.0. Front face of the glass at +z. Origin: the bounding-box centre, so
`Pos(x, y, z) * oled` puts the box centre at x, y, z. The PCB's front face is 3.565 mm above the origin,
the glass front 4.935 above it, the pin tips 4.935 below it. The header is on the +y side.
make_given.py writes the STEP.
"""
from build123d import Box, Cylinder, Pos

VENDOR = "Winstar"
SOURCE = ("Winstar WEA012864D-03 0.96 inch 128x64 COG+PCB OLED module (SSD1306BZ, I2C), "
          "OLED SPECIFICATION General Specification and Contour Drawing "
          "(https://blog.e-ika.com/wp-content/uploads/2020/02/oled096-datasheet.pdf, "
          "product page https://www.winstar.com.tw/products/oled-module/graphic-oled-display/4-pin-oled.html): "
          "27.30 x 27.30 x 2.37 mm, glass 26.7 x 19.26 mm, 4 x 2.5 mm holes 20.7 x 23.2 mm apart, "
          "header pins 7.5 mm behind the PCB")

PCB = (27.3, 27.3, 1.0)
GLASS = (26.7, 19.26, 2.37 - PCB[2])
HOLE_DIA = 2.5
HOLE_X, HOLE_Y = 20.7 / 2.0, 23.2 / 2.0
HEADER_Y = PCB[1] / 2.0 - 1.65          # pin row, from the PCB centre
PITCH, PINS = 2.54, 4
BODY_H, PIN_LEN, PIN_W = 1.5, 6.0, 0.6


def build():
    # PCB front face at z = 0, glass in front of it, header behind it.
    pcb = Pos(0, 0, -PCB[2] / 2.0) * Box(*PCB)
    for sx in (-1, 1):
        for sy in (-1, 1):
            pcb -= Pos(sx * HOLE_X, sy * HOLE_Y, -PCB[2] / 2.0) * Cylinder(HOLE_DIA / 2.0, PCB[2] + 2.0)
    oled = pcb + Pos(0, 0, GLASS[2] / 2.0) * Box(*GLASS)
    oled += Pos(0, HEADER_Y, -PCB[2] - BODY_H / 2.0) * Box(PITCH * PINS, PITCH, BODY_H)
    for i in range(PINS):
        x = (i - (PINS - 1) / 2.0) * PITCH
        oled += (Pos(x, HEADER_Y, -PCB[2] - BODY_H - PIN_LEN / 2.0)
                 * Box(PIN_W, PIN_W, PIN_LEN))
    top, bottom = GLASS[2], -(PCB[2] + BODY_H + PIN_LEN)
    return Pos(0, 0, -(top + bottom) / 2.0) * oled
