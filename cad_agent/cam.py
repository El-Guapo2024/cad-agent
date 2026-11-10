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
                 dressup=False, recipe=None):
        self.name, self.type_id, self.module = name, type_id, module
        self.command, self.menu, self.transaction, self.icon = command, menu, transaction, icon
        self.op, self.dressup = op, dressup
        self.recipe = recipe          # how a dress-up's command makes it (cam_replay.py), for the Gui-module ones


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
                     "Create MillFace", "CAM_Face", op=True),
    "Drilling": Kind("Drilling", "Path::FeaturePython", "Path.Op.Drilling", "CAM_Drilling", "Drilling",
                     "Create Drilling", "CAM_Drilling", op=True),
    # Op/Gui/<Op>.py SetupOperation(name, ..., pixmap, menuText): command CAM_<name>, transaction "Create <name>"
    "Helix": Kind("Helix", "Path::FeaturePython", "Path.Op.Helix", "CAM_Helix", "Helix",
                   "Create Helix", "CAM_Helix", op=True),
    "Engrave": Kind("Engrave", "Path::FeaturePython", "Path.Op.Engrave", "CAM_Engrave", "Engrave",
                     "Create Engrave", "CAM_Engrave", op=True),
    # no icon: FreeCAD's CAM_Vcarve.svg says CC-BY 4.0 and is not copied (ui/public/freecad-icons/README.md)
    "Vcarve": Kind("Vcarve", "Path::FeaturePython", "Path.Op.Vcarve", "CAM_Vcarve", "Vcarve",
                    "Create Vcarve", None, op=True),
    # Surface and Waterline need OpenCamLib (ui/opencamlib/build.sh); no icons: CAM_3DSurface.svg and CAM_Waterline.svg
    # are not among the copied icons
    "Surface": Kind("Surface", "Path::FeaturePython", "Path.Op.Surface", "CAM_Surface", "3D Surface",
                    "Create Surface", None, op=True),
    "Waterline": Kind("Waterline", "Path::FeaturePython", "Path.Op.Waterline", "CAM_Waterline", "Waterline",
                      "Create Waterline", None, op=True),
    "Slot": Kind("Slot", "Path::FeaturePython", "Path.Op.Slot", "CAM_Slot", "Slot", "Create Slot", "CAM_Slot", op=True),
    "Deburr": Kind("Deburr", "Path::FeaturePython", "Path.Op.Deburr", "CAM_Deburr", "Deburr",
                    "Create Deburr", "CAM_Deburr", op=True),
    "ThreadMilling": Kind("ThreadMilling", "Path::FeaturePython", "Path.Op.ThreadMilling", "CAM_ThreadMilling",
                          "Thread Milling", "Create ThreadMilling", "CAM_ThreadMilling", op=True),
    "Tapping": Kind("Tapping", "Path::FeaturePython", "Path.Op.Tapping", "CAM_Tapping", "Tapping",
                     "Create Tapping", "CAM_Tapping", op=True),
    "Pocket3D": Kind("Pocket3D", "Path::FeaturePython", "Path.Op.Pocket", "CAM_Pocket3D", "3D Pocket",
                      "Create Pocket3D", "CAM_3DPocket", op=True),
    "MillFacing": Kind("MillFacing", "Path::FeaturePython", "Path.Op.MillFacing", "CAM_MillFacing", "Mill Facing",
                        "Create MillFacing", "CAM_Face", op=True),
    "Adaptive": Kind("Adaptive", "Path::FeaturePython", "Path.Op.Adaptive", "CAM_Adaptive", "Adaptive",
                      "Create Adaptive", "CAM_Adaptive", op=True),
    "Custom": Kind("Custom", "Path::FeaturePython", "Path.Op.Custom", "CAM_Custom", "Custom",
                    "Create Custom", "CAM_Custom", op=True),
    "Probe": Kind("Probe", "Path::FeaturePython", "Path.Op.Probe", "CAM_Probe", "Probe",
                   "Create Probe", "CAM_Probe", op=True),
    "DressupTag": Kind("DressupTag", "Path::FeaturePython", "Path.Dressup.Tags", "CAM_DressupTag", "Tag",
                       "Create a Tag dressup", "CAM_Dressup", dressup=True),
    "DressupDogbone": Kind("DressupDogbone", "Path::FeaturePython", "Path.Dressup.DogboneII", "CAM_DressupDogbone",
                           "Dogbone", "Create Dogbone Dress-up", "CAM_Dressup", dressup=True),
    # Path/Op/Gui/Comment.py and Stop.py: the command's snippet makes the object and adds it to the job
    "Comment": Kind("Comment", "Path::FeaturePython", "Path.Op.Gui.Comment", "CAM_Comment", "Comment",
                    "Create a Comment in the CNC program", "CAM_Comment", op=True, recipe="snippet"),
    "Stop": Kind("Stop", "Path::FeaturePython", "Path.Op.Gui.Stop", "CAM_Stop", "Stop",
                 "Add Optional or Mandatory Stop to the program", "CAM_Stop", op=True, recipe="snippet"),
    # the dress-ups added 2026-11-06: Path/Dressup/Gui/<Name>.py's command (its id, MenuText, transaction, object name)
    "DressupLeadInOut": Kind("DressupLeadInOut", "Path::FeaturePython", "Path.Dressup.Gui.LeadInOut",
                              "CAM_DressupLeadInOut", "Lead In/Out", "Create LeadInOut Dressup",
                              "CAM_Dressup", dressup=True, recipe="gui_setup"),
    "DressupRampEntry": Kind("DressupRampEntry", "Path::FeaturePython", "Path.Dressup.Gui.RampEntry",
                              "CAM_DressupRampEntry", "Ramp Entry", "Create RampEntry Dressup",
                              "CAM_Dressup", dressup=True, recipe="gui_setup"),
    "DressupBoundary": Kind("DressupBoundary", "Path::FeaturePython", "Path.Dressup.Boundary",
                             "CAM_DressupPathBoundary", "Boundary", "Create Path Boundary Dress-up",
                             "CAM_Dressup", dressup=True, recipe="app"),
    "DressupBoundary2": Kind("DressupBoundary2", "Path::FeaturePython", "Path.Dressup.Gui.Boundary2",
                              "CAM_DressupPathBoundary2", "Boundary2", "Create Path Boundary Dress-up",
                              "CAM_Dressup", dressup=True, recipe="gui"),
    "DressupArray": Kind("DressupArray", "Path::FeaturePython", "Path.Dressup.Array",
                          "CAM_DressupArray", "Array", "Create Path Array Dress-up",
                          "CAM_Dressup", dressup=True, recipe="app"),
    "DressupDragknife": Kind("DressupDragknife", "Path::FeaturePython", "Path.Dressup.Gui.Dragknife",
                              "CAM_DressupDragKnife", "Drag Knife", "Create Dress-up",
                              "CAM_Dressup", dressup=True, recipe="dragknife"),
    "DressupMirror": Kind("DressupMirror", "Path::FeaturePython", "Path.Dressup.Gui.Mirror",
                           "CAM_DressupMirror", "Mirror", "Create Dress-up",
                           "CAM_Dressup", dressup=True, recipe="gui"),
    "DressupPlungeMilling": Kind("DressupPlungeMilling", "Path::FeaturePython", "Path.Dressup.Gui.PlungeMilling",
                                  "CAM_DressupPlungeMilling", "Plunge Milling", "Create PlungeMilling Dressup",
                                  "CAM_Dressup", dressup=True, recipe="gui"),
    "DressupZCorrect": Kind("DressupZCorrect", "Path::FeaturePython", "Path.Dressup.Gui.ZCorrect",
                             "CAM_DressupZCorrect", "Z Depth Correction", "Create Dress-up",
                             "CAM_Dressup", dressup=True, recipe="zcorrect"),
    "DressupAxisMap": Kind("DressupAxisMap", "Path::FeaturePython", "Path.Dressup.Gui.AxisMap",
                            "CAM_DressupAxisMap", "Axis Map", "Create Dress-up",
                            "CAM_Dressup", dressup=True, recipe="axismap"),
}
OPS = tuple(k for k, v in KINDS.items() if v.op)
DRESSUPS = tuple(k for k, v in KINDS.items() if v.dressup)
# the Create() name each kind's FreeCAD command gives the object
DEFAULT_NAMES = {"Job": "Job", "Profile": "Profile", "PocketShape": "Pocket_Shape", "MillFace": "MillFace",
                 "Drilling": "Drilling", "DressupTag": "DressupTag",
                 "DressupDogbone": "DressupDogbone",
                 "Helix": "Helix", "Engrave": "Engrave", "Vcarve": "Vcarve", "Surface": "Surface", "Waterline": "Waterline", "Slot": "Slot", "Deburr": "Deburr",
                 "ThreadMilling": "ThreadMilling", "Tapping": "Tapping", "Pocket3D": "Pocket3D",
                 "MillFacing": "MillFacing", "Adaptive": "Adaptive", "Custom": "Custom", "Probe": "Probe",
                 "Comment": "Comment", "Stop": "Stop",
                 "DressupLeadInOut": "DressupLeadInOut", "DressupRampEntry": "DressupRampEntry",
                 "DressupBoundary": "DressupPathBoundary", "DressupBoundary2": "DressupPathBoundary2",
                 "DressupArray": "DressupPathArray", "DressupDragknife": "DragknifeDressup",
                 "DressupMirror": "DressupMirror", "DressupPlungeMilling": "DressupPlungeMilling",
                 "DressupZCorrect": "ZCorrectDressup", "DressupAxisMap": "AxisMapDressup"}


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
Helix = _maker("Helix")
Engrave = _maker("Engrave")
Vcarve = _maker("Vcarve")
Surface = _maker("Surface")
Waterline = _maker("Waterline")
Slot = _maker("Slot")
Deburr = _maker("Deburr")
ThreadMilling = _maker("ThreadMilling")
Tapping = _maker("Tapping")
Pocket3D = _maker("Pocket3D")
MillFacing = _maker("MillFacing")
Adaptive = _maker("Adaptive")
Custom = _maker("Custom")
Probe = _maker("Probe")
DressupLeadInOut = _maker("DressupLeadInOut")
DressupRampEntry = _maker("DressupRampEntry")
DressupBoundary = _maker("DressupBoundary")
DressupBoundary2 = _maker("DressupBoundary2")
DressupArray = _maker("DressupArray")
DressupDragknife = _maker("DressupDragknife")
DressupMirror = _maker("DressupMirror")
DressupPlungeMilling = _maker("DressupPlungeMilling")
DressupZCorrect = _maker("DressupZCorrect")
DressupAxisMap = _maker("DressupAxisMap")
Comment = _maker("Comment")
Stop = _maker("Stop")
DressupTag = _maker("DressupTag")
DressupDogbone = _maker("DressupDogbone")

POSTS = ("linuxcnc", "grbl", "generic")
