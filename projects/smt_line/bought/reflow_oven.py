"""The NeoDen IN6 desktop conveyor reflow oven, drawn from its manual's photos. NeoDen publishes no CAD and no
dimensioned drawing, so the shape is measured off two photos and scaled to the published outline:

- Outline: user manual s2, 1020 x 507 x 350, soldering width 260, max height 30 above the belt, left to right.
- Side profile: the straight-on front photo in manual s3.1 (embedded image 9, 883 x 357 px). Across it the
  oven is 834 px for 1020 mm and 283 px for 350 mm, so 1.22 to 1.24 mm a pixel. Read off it:
  - the white base: full length, 199 high at the ends, with 36 x 30 chamfers top and bottom;
  - the hood: white, z 120 to 350, on a black band from z 83;
  - the black end caps: flared out to 16 mm from each end at z 279, back in to 121 mm at z 83.
- Ends: the entrance photo (embedded image 20, end-on, 1057 x 685 px). At the scale its own base gives
  (0.467 mm a pixel), its mesh comes out 271 wide against the published 260 soldering width, so the scale
  holds. Read off it:
  - the mesh top: 66 above the oven's bottom, on an end roller at the very end;
  - the pocket the belt runs out into: 397 wide between the white wings, its lip 48 up, open to about 121;
  - the mouth into the hood: about 310 wide.
  These are read through a lens, so take them to about +-8 mm.

VERIFIED is False until someone measures a real IN6. Its belt height sets the whole line's height.
The heaters, fans and fume filter inside are not drawn. A board only meets the belt, the tunnel and the pockets.

Frame: the oven's bottom at z 0, its entry end at x 0, the belt centred on y 0.
"""
from build123d import Box, Cylinder, Plane, Polyline, Pos, Rot, extrude, make_face

SOURCE = ("NeoDen IN6 user manual (16 p): s2 outline 1020 x 507 x 350, 260 soldering width, 30 max height; "
          "side profile and belt measured off the s3.1 front photo and the entrance photo, scaled to that outline")
VENDOR = "NeoDen (reference only; any 260-wide desktop conveyor oven)"
VERIFIED = False
MATERIAL = "steel"
MASS_G = 49000.0
MASS_SOURCE = "NeoDen IN6 user manual s2, net weight 49 kg"

PARAMS = {"length": 1020.0, "depth": 507.0, "height": 350.0, "belt_z": 66.0, "clear": 30.0, "mesh": 271.0,
          "mouth": 310.0, "pocket": 397.0, "lip": 48.0, "pocket_top": 121.0, "cap": 121.0}


def _side(pts, depth):
    """A side-profile polygon (x along the oven, z up), extruded through the oven's full depth."""
    return extrude(Plane.XZ * make_face(Polyline(*pts, close=True)), amount=depth / 2, both=True)


def build(length, depth, height, belt_z, clear, mesh, mouth, pocket, lip, pocket_top, cap):
    L, H = length, height
    base = _side([(0, 28), (36, 0), (L - 36, 0), (L, 28), (L, 170), (L - 36, 199), (36, 199), (0, 170)], depth)
    hood = _side([(cap, 83), (L - cap, 83), (L - 94, 114), (L - 21, 224), (L - 16, H - 71), (L - 138, H),
                  (138, H), (16, H - 71), (21, 224), (94, 114)], depth)
    body = base + hood
    # the open pockets at each end, where the belt runs out over its end roller
    for x in (cap / 2 - 1, L - cap / 2 + 1):
        body -= Pos(x, 0, (lip + pocket_top) / 2) * Box(cap + 2, pocket, pocket_top - lip)
    # the tunnel through the hood: the board rides on the belt with `clear` above it
    body -= Pos(L / 2, 0, belt_z + clear / 2) * Box(L + 2, mouth, clear)
    # the mesh belt out in each pocket: a plate to the pocket's end and the end roller under it
    r = 8.0
    for x0, x1 in ((20.0, cap), (L - cap, L - 20.0)):
        body += Pos((x0 + x1) / 2, 0, belt_z - r / 2) * Box(x1 - x0, mesh, r)
        xr = x0 if x0 < L / 2 else x1
        body += Pos(xr, 0, belt_z - r) * Rot(90, 0, 0) * Cylinder(r, pocket)
    return body
