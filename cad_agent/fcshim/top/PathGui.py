# SPDX-License-Identifier: LGPL-2.1-or-later
"""FreeCAD's PathGui (the CAM workbench's C++ GUI module) with no GUI: an inert stand-in."""
from PySide._dummy import module_getattr


def __getattr__(name):
    return module_getattr(name)
