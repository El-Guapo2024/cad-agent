# SPDX-License-Identifier: LGPL-2.1-or-later
# Port of FreeCAD 3160daf1e2b6's Assembly_InsertNewPart (src/Mod/Assembly/CommandInsertNewPart.py and
# UtilsAssembly.createPart, Copyright (c) 2023 Ondsel <development@ondsel.com>).
"""Assembly_InsertNewPart: a new part, linked into the Assembly, its origin jointed where the panel's pick says.

FreeCAD's TaskAssemblyNewPart is the joint panel (a Fixed joint) whose first reference is a new, empty App::Link
("Link"); the second is the element picked in the 3D view. At OK the joint is kept when it has both (the link,
unconnected, ends up as Reference2 and is presolved onto the pick), then createPart makes an App::Part "Part" holding a
PartDesign Body with a Sketch on its XY_Plane (a circle of radius 5, "as a base shape for visualisation") and the link
takes it, Label the part's. Here a part is a part file of its own (FreeCAD's "Create part in new file", which is how
every part is kept), so createPart writes parts/<Part>.py: that Body and Sketch.
"""
from __future__ import annotations

TEMPLATE = '''"""{part}: a new part of the Assembly (Assembly_InsertNewPart), a PartDesign Body to model.

Its shape is FEATURES, the Body's tree in FreeCAD's order (cad_agent/feature.py). The workbench edits the
lists in place; so can you.
"""
from cad_agent.feature import (ArcOfCircle, ArcOfEllipse, ArcOfHyperbola, ArcOfParabola, Body, BSplineCurve,
                               Circle, Constraint, Ellipse, LineSegment, Pad, Pocket, Point, Sketch)

MATERIAL = {material!r}
PROCESS = {process!r}

PARAMS = {{}}

FEATURES = [
    Sketch("Sketch", support="XY", geometry=[Circle((0.0, 0.0), 5.0)], constraints=[]),
]


def build(**p):
    return Body(FEATURES, p)
'''


def part_source(part: str, material: str = "petg", process: str = "fdm") -> str:
    """UtilsAssembly.createPart: the Body with its Sketch on XY_Plane holding a circle of radius 5."""
    return TEMPLATE.format(part=part, material=material, process=process)


def empty_shape():
    """The new link's shape while the panel is open: nothing yet (its reference is the whole part, its origin)."""
    from OCP.BRep import BRep_Builder
    from OCP.TopoDS import TopoDS_Compound
    c = TopoDS_Compound()
    BRep_Builder().MakeCompound(c)
    return c
