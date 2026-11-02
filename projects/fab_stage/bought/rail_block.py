"""rail_block: HIWIN MGN15H carriage (heavy load block).

Copied from the library entry mgn15h by `cad lib use`; where each number came from is in rail_block.json
and in `cad lib info mgn15h`.
It is meant to be left alone: `cad lib use <project> mgn15h --as rail_block --replace`
writes it again, and `cad lib check <project>` fails when this file no longer hashes to the pin in the sidecar.
"""

PARAMS = {}                      # fixed: the sidecar's mass is the mass of exactly this part

ARGS = {
    'length': 58.8,
    'width': 32.0,
    'height': 16.0,
    'base_gap': 4.0,
    'rail_width': 15.0,
    'hole_pitch_along': 25.0,
    'hole_pitch_across': 25.0,
    'tap_depth': 4.0,
    'tap_dia': 2.5,
    'rail_gap': 0.2,
}


def build():
    from cad_agent.library.gen.mgn import carriage
    return carriage(**ARGS)
