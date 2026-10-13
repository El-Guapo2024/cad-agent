"""mgn12_rail: HIWIN MGNR12R miniature linear guide rail, length 150 mm.

Copied from the library entry mgn12-rail by `cad lib use`; where each number came from is in mgn12_rail.json
and in `cad lib info mgn12-rail`.
It is meant to be left alone: `cad lib use <project> mgn12-rail length=150 --as mgn12_rail --replace`
writes it again, and `cad lib check <project>` fails when this file no longer hashes to the pin in the sidecar.
"""

PARAMS = {}                      # fixed: the sidecar's mass is the mass of exactly this part

ARGS = {
    'width': 12.0,
    'height': 8.0,
    'pitch': 25.0,
    'counterbore_dia': 6.0,
    'counterbore_depth': 4.5,
    'hole_dia': 3.5,
    'end_min': 5.0,
    'length': 150.0,
}


def build():
    from cad_agent.library.gen.mgn import rail
    return rail(**ARGS)
