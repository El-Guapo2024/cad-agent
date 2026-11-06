# SPDX-License-Identifier: LGPL-2.1-or-later
"""FreeCADGui with no GUI, for the CAM dress-ups whose object classes live in FreeCAD's Gui modules
(Path/Dressup/Gui/*.py): addCommand keeps nothing, every other name is an inert stand-in (PySide/_dummy.py)."""
from PySide._dummy import module_getattr


def addCommand(name, command):
    pass


def __getattr__(name):
    return module_getattr(name)
