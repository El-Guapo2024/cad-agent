# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It names FreeCAD's CAM document objects as FreeCAD's CAM workbench makes them and keeps
# FreeCAD's licence, the GNU Lesser General Public License, version 2.1 or (at your option) any later version; the
# text is in ../ui/LICENSE. FreeCAD (https://github.com/FreeCAD/FreeCAD), commit 3160daf1e2b6. See ../NOTICE.
"""A CAM Job of a project: cam/<Job>.py's JOB list (docs/EDITING_PLAN.md, "CAM in a project").

Each entry is one of FreeCAD's CAM objects, a call with the object's Name and the properties set on it after FreeCAD's
Create() made it, by FreeCAD's own property names:

    CAM.Job("Job", Model=["plate"], PostProcessor="linuxcnc")
    CAM.ToolBit("ToolBit", Bit="5mm_Endmill", Diameter="6 mm")          # a library bit (Mod/CAM/Tools/Bit/*.fctb)
    CAM.ToolController("TC__5mm_Endmill", Tool="ToolBit", ToolNumber=2, HorizFeed="600 mm/min")
    CAM.Profile("Profile", Base=[("plate", ["Face3"])], StepDown="2 mm", ExpressionEngine={"StepDown": None})
    CAM.DressupTag("DressupTag", Base="Profile")

The file is plain Python: importing it gives the list of Entry objects; the app and `cad cam ...` read and edit it
(cad_agent/cam_edit.py) and cad_agent/cam_doc.py replays it into FreeCAD's own CAM code. This module imports nothing
heavy."""
from __future__ import annotations

FREECAD_COMMIT = "3160daf1e2b6"


class CamError(ValueError):
    pass


class Kind:
    """What an entry is: FreeCAD's TypeId, the module whose Create() makes it, the GUI command and transaction."""

    def __init__(self, name, type_id, module=None, command=None, menu=None, transaction=None, icon=None, op=False,
                 dressup=False):
        self.name, self.type_id, self.module = name, type_id, module
        self.command, self.menu, self.transaction, self.icon = command, menu, transaction, icon
        self.op, self.dressup = op, dressup


KINDS = {
    "Job": Kind("Job", "Path::FeaturePython", "Path.Main.Job", "CAM_Job", "Job", "Create Job", "CAM_Job"),
    "Stock": Kind("Stock", "Part::FeaturePython", "Path.Main.Stock", icon="CAM_Stock"),
    "SetupSheet": Kind("SetupSheet", "App::FeaturePython", "Path.Base.SetupSheet", icon="CAM_SetupSheet"),
    "ToolBit": Kind("ToolBit", "Part::FeaturePython", "Path.Tool.toolbit", icon="CAM_ToolBit"),
    "ToolController": Kind("ToolController", "Path::FeaturePython", "Path.Tool.Controller",
                           transaction="Add Tool Controller to the Job", icon="CAM_ToolController"),
    "Profile": Kind("Profile", "Path::FeaturePython", "Path.Op.Profile", "CAM_Profile", "Profile",
                    "Create Profile", "CAM_Profile", op=True),
    "PocketShape": Kind("PocketShape", "Path::FeaturePython", "Path.Op.PocketShape", "CAM_Pocket_Shape",
                        "Pocket Shape", "Create Pocket Shape", "CAM_Pocket", op=True),
    "MillFace": Kind("MillFace", "Path::FeaturePython", "Path.Op.MillFace", "CAM_MillFace", "Face",
                     "Create Face", "CAM_Face", op=True),
    "Drilling": Kind("Drilling", "Path::FeaturePython", "Path.Op.Drilling", "CAM_Drilling", "Drilling",
                     "Create Drilling", "CAM_Drilling", op=True),
    "Adaptive": Kind("Adaptive", "Path::FeaturePython", "Path.Op.Adaptive", "CAM_Adaptive", "Adaptive",
                     "Create Adaptive", "CAM_Adaptive", op=True),
    "DressupTag": Kind("DressupTag", "Path::FeaturePython", "Path.Dressup.Tags", "CAM_DressupTag", "Tag",
                       "Create Tag Dress-up", "CAM_Dressup", dressup=True),
    "DressupDogbone": Kind("DressupDogbone", "Path::FeaturePython", "Path.Dressup.DogboneII", "CAM_DressupDogbone",
                           "Dogbone", "Create Dogbone Dress-up", "CAM_Dressup", dressup=True),
}
OPS = tuple(k for k, v in KINDS.items() if v.op)
DRESSUPS = tuple(k for k, v in KINDS.items() if v.dressup)
# the Create() name each kind's FreeCAD command gives the object
DEFAULT_NAMES = {"Job": "Job", "Profile": "Profile", "PocketShape": "Pocket_Shape", "MillFace": "MillFace",
                 "Drilling": "Drilling", "Adaptive": "Adaptive", "DressupTag": "DressupTag",
                 "DressupDogbone": "DressupDogbone"}


class Entry:
    """One object of the JOB list: its kind, Name and the properties the file sets, in the file's order."""

    def __init__(self, kind: str, name: str, props: dict | None = None):
        if kind not in KINDS:
            raise CamError(f"{kind!r} is not a CAM object the app knows ({', '.join(KINDS)})")
        if not isinstance(name, str) or not name:
            raise CamError(f"a {kind} needs a name")
        self.kind = kind
        self.name = name
        self.props = dict(props or {})

    def copy(self):
        return Entry(self.kind, self.name, {k: _copy(v) for k, v in self.props.items()})

    def as_dict(self):
        return {"kind": self.kind, "name": self.name, "props": _jsonable(self.props)}

    def __eq__(self, o):
        return isinstance(o, Entry) and (self.kind, self.name, _jsonable(self.props)) == (o.kind, o.name,
                                                                                         _jsonable(o.props))

    def __repr__(self):
        return f"CAM.{self.kind}({self.name!r})"


def _copy(v):
    if isinstance(v, dict):
        return {k: _copy(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_copy(x) for x in v]
    if isinstance(v, tuple):
        return tuple(_copy(x) for x in v)
    return v


def _jsonable(v):
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    return v


def _maker(kind):
    def make(name, **props):
        return Entry(kind, name, props)
    make.__name__ = kind
    make.__doc__ = f"CAM.{kind}(Name, **FreeCAD properties): a JOB entry."
    return make


Job = _maker("Job")
Stock = _maker("Stock")
SetupSheet = _maker("SetupSheet")
ToolBit = _maker("ToolBit")
ToolController = _maker("ToolController")
Profile = _maker("Profile")
PocketShape = _maker("PocketShape")
MillFace = _maker("MillFace")
Drilling = _maker("Drilling")
Adaptive = _maker("Adaptive")
DressupTag = _maker("DressupTag")
DressupDogbone = _maker("DressupDogbone")

POSTS = ("linuxcnc", "grbl", "generic")
