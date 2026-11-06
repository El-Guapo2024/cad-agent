"""The Draft workbench's runtime: FreeCAD's own Draft Python (cad_agent/fcdraft/Mod/Draft, the modules that do not need the
GUI, vendored unchanged) importable over the stand-ins for FreeCAD's C++ (cad_agent/fcshim/top), as cam_runtime does for
CAM. FreeCAD's Draft goes before the stand-ins' own small Draft and draftutils (what CAM's Python asks of them)."""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DRAFT = HERE / "fcdraft" / "Mod" / "Draft"
_active = False


def activate():
    global _active
    if _active:
        return
    from . import cam_runtime
    cam_runtime.activate()
    for name in [m for m in sys.modules if m == "Draft" or m == "draftutils" or m.startswith("draftutils.")]:
        del sys.modules[name]                  # the stand-ins' Draft, should CAM have loaded it
    if str(DRAFT) in sys.path:
        sys.path.remove(str(DRAFT))
    sys.path.insert(0, str(DRAFT))
    from PySide import QtCore
    QtCore.RESOURCE_DIRS[":/ui/"] = str(DRAFT / "Resources" / "ui")    # draftutils.params reads the preference .ui
    _active = True
