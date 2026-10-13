"""extrusion_2020: 20 x 20 T-slot aluminium extrusion, 6 mm slots, the real section, length 260 mm, axis x.

Copied from the library entry extrusion-2020 by `cad lib use`; where each number came from is in extrusion_2020.json
and in `cad lib info extrusion-2020`.
It is meant to be left alone: `cad lib use <project> extrusion-2020 length=260 axis=x --as extrusion_2020 --replace`
writes it again, and `cad lib check <project>` fails when this file no longer hashes to the pin in the sidecar.
"""

PARAMS = {}                      # fixed: the sidecar's mass is the mass of exactly this part

ARGS = {
    'width': 20.0,
    'height': 20.0,
    'corner': 1.5,
    'neck': 2.9,
    'lead': 3.7,
    'lead_t': 0.737,
    'lip': 1.537,
    'cavity': 5.9,
    'shoulder_t': 2.945,
    'floor': 5.5,
    'floor_s': 3.345,
    'notch_s': 0.926,
    'notch_t': 6.034,
    'core_r': 2.8,
    'ear_root': [1.285, 2.488],
    'ear_tip': [1.887, 2.948],
    'length': 260.0,
    'axis': 'x',
}


def build():
    from cad_agent.library.gen.extrusion import tslot6
    return tslot6(**ARGS)
