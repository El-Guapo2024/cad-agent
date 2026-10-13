"""nema8: NEMA 8 stepper motor, 1.8 degree, 42 mm body (Nanotec ST2018M0804-A).

Copied from the library entry nema8 by `cad lib use`; where each number came from is in nema8.json
and in `cad lib info nema8`.
It is meant to be left alone: `cad lib use <project> nema8 --as nema8 --replace`
writes it again, and `cad lib check <project>` fails when this file no longer hashes to the pin in the sidecar.
"""

PARAMS = {}                      # fixed: the sidecar's mass is the mass of exactly this part

ARGS = {
    'face': 20.0,
    'length': 42.0,
    'corner_radius': 1.5,
    'pilot_dia': 15.0,
    'pilot_height': 1.5,
    'shaft_dia': 4.0,
    'shaft_length': 16.5,
    'hole_pitch': 16.0,
    'hole_depth': 3.0,
    'hole_dia': 1.6,
}


def build():
    from cad_agent.library.gen.nema import motor
    return motor(**ARGS)
