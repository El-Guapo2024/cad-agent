# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses FreeCAD's PathApp module (src/Mod/CAM/App/AppPathPy.cpp, Copyright (c) 2014
# Yorik van Havre) and keeps FreeCAD's licence, the GNU Lesser General Public License, version 2.1 or (at your option)
# any later version; the text is in ../../../ui/LICENSE. FreeCAD (https://github.com/FreeCAD/FreeCAD), commit
# 3160daf1e2b6. See ../../../NOTICE.
"""PathApp, the C++ half of FreeCAD's `Path` package (Path/__init__.py does `from PathApp import *`): Command, Path,
Area, fromShapes and sortWires (cad_agent/fcshim/_fc_path.py, _fc_area.py)."""
from cad_agent.fcshim._fc_path import Command, Path  # noqa: F401


def __getattr__(name):
    if name in ("Area", "fromShapes", "sortWires", "FeatureArea", "FeatureAreaView"):
        from cad_agent.fcshim import _fc_area
        return getattr(_fc_area, name)
    raise AttributeError(f"module 'PathApp' has no attribute '{name}'")


def write(obj, filename):
    with open(filename, "w") as f:
        f.write(obj.Path.toGCode())


def read(filename, document=None):
    raise NotImplementedError("Path.read")


def show(path, name="Path"):
    return None
