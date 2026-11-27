"""A 6-zone desktop conveyor reflow oven, as an envelope: the NeoDen IN6's published outline with its conveyor
tunnel. The insides (heaters, fans, mesh belt) are not drawn; nothing in the line reaches them.

From the IN6 user manual (16 p, Wayback copy in smt-references/5-reflow/conveyor-ovens), section 2: outside
1020 x 507 x 350, soldering width 260, standard height max 30 (above the belt), left to right, 49 kg, 700 W
working. NOT published, so VERIFIED is False: how high the belt is above the bench (belt_z here is the line's
height, set from the only desktop oven that publishes one, a 3-zone mesh-belt oven on DigiKey: 300 mm), and
where along the length the belt begins (taken as the end faces).

Frame: the bench at z 0, the entry face at x 0, the tunnel centred on y 0.
"""
from build123d import Box, Pos

SOURCE = "NeoDen IN6 user manual s2 (outline, width, max height); belt height from DigiKey 3-zone oven sheet 114991685"
VENDOR = "NeoDen (reference only; any 260-wide desktop conveyor oven)"
VERIFIED = False
MATERIAL = "steel"
MASS_G = 49000.0
MASS_SOURCE = "NeoDen IN6 user manual s2, net weight 49 kg"

PARAMS = {"length": 1020.0, "depth": 507.0, "height": 350.0, "width": 260.0, "clear": 30.0, "belt_z": 300.0}


def build(length, depth, height, width, clear, belt_z):
    body = Pos(length / 2, 0, height / 2) * Box(length, depth, height)
    return body - Pos(length / 2, 0, belt_z + clear / 2) * Box(length + 2, width, clear)
