"""y_rail: HIWIN MGNR15R miniature linear guide rail, length 720 mm.

Copied from the library entry mgn15-rail by `cad lib use`; where each number came from is in y_rail.json
and in `cad lib info mgn15-rail`.
It is meant to be left alone: `cad lib use <project> mgn15-rail length=720 --as y_rail --replace`
writes it again, and `cad lib check <project>` fails when this file no longer hashes to the pin in the sidecar.
"""

PARAMS = {}                      # fixed: the sidecar's mass is the mass of exactly this part

ARGS = {
    'width': 15.0,
    'height': 10.0,
    'pitch': 40.0,
    'counterbore_dia': 6.0,
    'counterbore_depth': 4.5,
    'hole_dia': 3.5,
    'end_min': 6.0,
    'length': 720.0,
}


def build():
    from cad_agent.library.gen.mgn import rail
    return rail(**ARGS)
