# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses FreeCAD's TechDraw module function findShapeOutline (src/Mod/TechDraw/App/
# AppTechDrawPy.cpp, Copyright (c) 2002 Jürgen Riegel) and keeps FreeCAD's licence, the GNU Lesser General Public
# License, version 2.1 or (at your option) any later version; the text is in ../../../ui/LICENSE. FreeCAD
# (https://github.com/FreeCAD/FreeCAD), commit 3160daf1e2b6. See ../../../NOTICE.
"""FreeCAD's TechDraw module for the CAM workbench's Python (cad_agent/fcshim): findShapeOutline, which Adaptive asks
for the stock's outline. The port is cad_agent/techdraw_outline.py, the app's TechDraw code."""
from cad_agent.fcshim._fc_part import Shape, topods, wrap
from cad_agent.fcshim._fc_base import Vector


def findShapeOutline(shape, scale, direction):
    """findShapeOutline(shape, scale, direction): the outer Wire of the shape seen along direction, or None."""
    from cad_agent.techdraw_outline import find_shape_outline
    if not isinstance(shape, Shape):
        raise TypeError("expected arg1 to be 'Shape'")
    if not isinstance(direction, Vector):
        raise TypeError("expected arg3 to be 'Vector'")
    w = find_shape_outline(topods(shape), float(scale), (direction.x, direction.y, direction.z))
    return None if w is None else wrap(w)
