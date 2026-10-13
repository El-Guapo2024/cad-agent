"""mgn12h: HIWIN MGN12H carriage (heavy load block).

Copied from the library entry mgn12h by `cad lib use`; where each number came from is in mgn12h.json
and in `cad lib info mgn12h`.
It is meant to be left alone: `cad lib use <project> mgn12h --as mgn12h --replace`
writes it again, and `cad lib check <project>` fails when this file no longer hashes to the pin in the sidecar.
"""

PARAMS = {}                      # fixed: the sidecar's mass is the mass of exactly this part

ARGS = {
    'length': 45.4,
    'width': 27.0,
    'height': 13.0,
    'base_gap': 3.0,
    'rail_width': 12.0,
    'hole_pitch_along': 20.0,
    'hole_pitch_across': 20.0,
    'tap_depth': 3.5,
    'tap_dia': 2.5,
    'rail_gap': 0.2,
}


def build():
    from cad_agent.library.gen.mgn import carriage
    return carriage(**ARGS)
