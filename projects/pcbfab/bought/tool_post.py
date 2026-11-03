"""tool_post: 40 x 40 T-slot aluminium extrusion, 8 mm slots, the real section, length 300.02 mm, axis z.

Copied from the library entry extrusion-4040 by `cad lib use`; where each number came from is in tool_post.json
and in `cad lib info extrusion-4040`.
It is meant to be left alone: `cad lib use <project> extrusion-4040 length=300.02 axis=z --as tool_post --replace`
writes it again, and `cad lib check <project>` fails when this file no longer hashes to the pin in the sidecar.
"""

PARAMS = {}                      # fixed: the sidecar's mass is the mass of exactly this part

ARGS = {
    'width': 40.0,
    'corner': 4.0,
    'neck': 4.1,
    'lead': 5.6,
    'hook_t': 3.65,
    'hook_r': 1.0,
    'hook_top': 4.65,
    'hook_out': 7.1,
    'wing_c': [7.6, 4.485],
    'wing_r': 2.5,
    'wall': 10.1,
    'shoulder_r': 5.0,
    'shoulder_t': 5.708,
    'floor': 12.4,
    'floor_half': 3.408,
    'chamber_lo': 11.8,
    'chamber_hi': 18.2,
    'chamber_r': 2.2,
    'bore_r': 3.35,
    'length': 300.02,
    'axis': 'z',
}


def build():
    from cad_agent.library.gen.extrusion import tslot8
    return tslot8(**ARGS)
