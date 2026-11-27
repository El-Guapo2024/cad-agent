"""A stand under the pick-and-place, so its board height meets the oven's. Bought, not designed: any bench shelf
or table of this height does (NeoDen stands its IN6 on a pedestal for the same reason, manual s3.3). The size is
the LumenPnP's leg-extension footprint plus 1.5 mm a side; the height is what the line height leaves.

Frame: its top at z 0, its front-left corner at x -13, y -106 (the LumenPnP's own frame, which it sits under).
"""
from build123d import Box, Pos

SOURCE = "any bench shelf or stand of this size; footprint from the LumenPnP legs (pnp_v4.step)"
VENDOR = None
VERIFIED = False                 # not chosen yet

PARAMS = {"x0": -13.0, "x1": 613.0, "y0": -106.0, "y1": 570.0, "height": 158.33}


def build(x0, x1, y0, y1, height):
    return Pos((x0 + x1) / 2, (y0 + y1) / 2, -height / 2) * Box(x1 - x0, y1 - y0, height)
