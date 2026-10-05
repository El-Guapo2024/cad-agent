"""16 mm panel-mount momentary pushbutton, as the envelope a panel has to clear.

This is not a model of the switch. It is the part that goes through the hole (the threaded barrel), the
push cap in front, and the solder tabs behind. The flange (18.06 mm) and the mounting nut bear on the
front and back faces of the panel, so they are left out: the only thing between this body and the panel
is the cutout, and that is what the task grades.

Figures, Adafruit "16mm Panel Mount Momentary Pushbutton" (product 1502 family), Technical Details on the
product page:

    Shaft Dimensions   14.89 x 15.56 x 18.7 mm    read as the barrel: 15.56 round, 14.89 across
                                                  the two flats, 18.7 long
    Button Height      5 mm                       cap, taken from the panel face
    Max Dimensions     18.06 x 18 x 29.4 mm       the flange is the 18.06; 29.4 is the
                                                  overall length, so the tabs are 5.7
                                                  long (29.4 - 5.0 - 18.7)

and its drawing (cdn-shop.adafruit.com/datasheets/R13diagram.jpg): a round M16.0 x 1.0 thread with two
flats 15.0 apart, cap diameter 13.0, tabs 0.7 thick on 9.5 centres and 3.2 wide. The drawing's nominal 16.0
outline is the mounting hole the product is sold for; the page measures the barrel at 15.56, which leaves
0.22 mm all round in a 16.0 hole.

Axis along z, flats facing +-y. Origin: the bounding-box centre, so `Pos(x, y, z) * push_button` puts the
box centre at x, y, z. The seat plane (where the panel's front face meets the barrel) is 9.7 mm above the
origin, the cap top 14.7 mm above it, the tab tips 14.7 mm below it. make_given.py writes the STEP.
"""
from build123d import Box, Cylinder, Pos

VENDOR = "Adafruit"
SOURCE = ("Adafruit 16mm Panel Mount Momentary Pushbutton, https://www.adafruit.com/product/1502 "
          "(Technical Details: shaft 14.89 x 15.56 x 18.7 mm, button height 5 mm, max 18.06 x 18 x 29.4 mm) "
          "and https://cdn-shop.adafruit.com/datasheets/R13diagram.jpg (M16 x 1.0, cap 13.0, tabs 0.7 x 3.2 "
          "on 9.5 mm). Envelope: flange and nut not modelled.")

BARREL_ROUND = 15.56        # across the thread crests
BARREL_FLATS = 14.89        # across the two flats
BARREL_LEN = 18.7
CAP_DIA = 13.0
CAP_H = 5.0                 # above the panel face
OVERALL = 29.4
TAB_T, TAB_W, TAB_PITCH = 0.7, 3.2, 9.5
TAB_LEN = OVERALL - CAP_H - BARREL_LEN


def build():
    # Seat plane at z = 0, cap above it, barrel and tabs below.
    barrel = Pos(0, 0, -BARREL_LEN / 2.0) * Cylinder(BARREL_ROUND / 2.0, BARREL_LEN)
    barrel &= Pos(0, 0, -BARREL_LEN / 2.0) * Box(BARREL_ROUND + 2.0, BARREL_FLATS, BARREL_LEN)
    body = barrel + Pos(0, 0, CAP_H / 2.0) * Cylinder(CAP_DIA / 2.0, CAP_H)
    for sx in (-1, 1):
        body += (Pos(sx * TAB_PITCH / 2.0, 0, -BARREL_LEN - TAB_LEN / 2.0)
                 * Box(TAB_T, TAB_W, TAB_LEN))
    middle = (CAP_H - BARREL_LEN - TAB_LEN) / 2.0
    return Pos(0, 0, -middle) * body
