"""feature_plate: one part made of PartDesign features (parts/plate.py), so the gates and `cad verify` run on a
feature list as they run on any part. It is a regression fixture, not a design anyone will build.

Frame: x across the plate, y along it, z up; z = 0 is the plate's underside, centred on x = y = 0.
"""
from cad_agent.state import build_part

SLUG = "feature_plate"


def parts():
    plate, _ = build_part(SLUG, "plate")
    return {"plate": plate}
