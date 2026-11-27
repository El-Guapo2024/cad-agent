"""A stand under a module, so its board height meets the line's. Bought, not designed: any block, shelf or
table of this size does. NeoDen stands its IN6 on a pedestal for the same reason (manual s3.3).

Here it goes under the oven, because the LumenPnP already sits on the bench as Opulo built it. Its board
is 141.7 above the bench and the IN6's belt only 66 above its own bottom, so the oven needs 75.7 under it.

Frame: its top at z 0, centred on x and y.
"""
from build123d import Box, Pos

SOURCE = "any block or bench shelf of this size; footprint the IN6's outline (manual s2)"
VENDOR = None
VERIFIED = False                 # not chosen yet

PARAMS = {"length": 1020.0, "depth": 507.0, "height": 75.7}


def build(length, depth, height):
    return Pos(0, 0, -height / 2) * Box(length, depth, height)
