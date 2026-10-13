"""extrusion_2040: 20 x 40 T-slot aluminium extrusion, 6 mm slots, the real section, length 640 mm, axis x.

Copied from the library entry extrusion-2040 by `cad lib use`; where each number came from is in extrusion_2040.json
and in `cad lib info extrusion-2040`.
It is meant to be left alone: `cad lib use <project> extrusion-2040 length=640 axis=x --as extrusion_2040 --replace`
writes it again, and `cad lib check <project>` fails when this file no longer hashes to the pin in the sidecar.
"""

PARAMS = {}                      # fixed: the sidecar's mass is the mass of exactly this part

ARGS = {
    'width': 20.0,
    'height': 40.0,
    'corner': 1.3,
    'neck': 3.0,
    'lead': 3.75,
    'lead_t': 0.75,
    'lip': 1.56,
    'cavity': 6.0,
    'shoulder_t': 3.0,
    'floor': 5.5,
    'floor_s': 3.431,
    'notch_s': 0.901,
    'notch_t': 6.02,
    'core_r': 2.75,
    'ear_root': [1.259, 2.508],
    'ear_tip': [1.788, 2.931],
    'chamber': [[0.0, 6.016], [0.901, 5.496], [3.432, 5.496], [6.3, 2.55], [8.44, 2.55]],
    'length': 640.0,
    'axis': 'x',
}


def build():
    from cad_agent.library.gen.extrusion import tslot6
    return tslot6(**ARGS)
