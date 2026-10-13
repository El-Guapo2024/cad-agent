"""A beam on two steel blocks, 600 mm apart, that may sag 50 um at midspan under 2.5 kg.

Coordinates: x along the beam, y across it, z up; z = 0 is the bench the two support blocks stand on, centred on
x = 0. The beam is the library's 20 x 40 extrusion, 640 mm long, so it rests 20 mm on each block. The extrusion
is drawn with its long side along y, which is flat for a load along z, so it is turned a quarter about x to stand
on its 40 mm side: the second moment about the axis a vertical load bends it round is then 46514 mm^4, not 12134.
"""
from build123d import Pos, Rot
from cad_agent.state import bought_solid

SLUG = "beam_deflection"

SUPPORT = 40.0           # the given blocks are 40 mm cubes
SPAN = 600.0             # clear distance between their inner faces
BEAM_LENGTH = 640.0      # rests 20 mm on each block

ALLOW_CONTACT = {"beam|support_left", "beam|support_right"}


def parts():
    block = bought_solid(SLUG, "support")
    beam = Rot(90, 0, 0) * bought_solid(SLUG, "extrusion_2040")      # the 40 mm side up
    reach = SPAN / 2.0 + SUPPORT / 2.0
    box = beam.bounding_box()
    return {
        "support_left": Pos(-reach, 0, SUPPORT / 2.0) * block,
        "support_right": Pos(reach, 0, SUPPORT / 2.0) * block,
        "beam": Pos(0, 0, SUPPORT - box.min.Z) * beam,               # its underside on the blocks' top faces
    }
