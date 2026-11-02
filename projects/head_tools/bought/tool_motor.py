"""tool_motor: NEMA 17 stepper motor, 1.8 degree, 34, 40 or 48 mm body, length 34.

Copied from the library entry nema17 by `cad lib use`; where each number came from is in tool_motor.json
and in `cad lib info nema17`.
It is meant to be left alone: `cad lib use <project> nema17 length=34 --as tool_motor --replace`
writes it again, and `cad lib check <project>` fails when this file no longer hashes to the pin in the sidecar.
"""

PARAMS = {}                      # fixed: the sidecar's mass is the mass of exactly this part

ARGS = {
    'face': 42.3,
    'pilot_dia': 22.0,
    'pilot_height': 2.03,
    'shaft_dia': 5.0,
    'shaft_length': 23.88,
    'hole_pitch': 31.0,
    'hole_depth': 4.5,
    'hole_dia': 2.5,
    'length': 34,
}


def build():
    from cad_agent.library.gen.nema import motor
    return motor(**ARGS)
