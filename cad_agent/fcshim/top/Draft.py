# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses what FreeCAD's Draft.clone does for one object (src/Mod/Draft/draftmake/
# make_clone.py and draftobjects/clone.py, Copyright (c) 2009, 2010 Yorik van Havre, 2009, 2010 Ken Cline, 2020 Eliud
# Cabrera Castillo) and keeps FreeCAD's licence, the GNU Lesser General Public License, version 2.1 or (at your option)
# any later version; the text is in ../../../ui/LICENSE. FreeCAD (https://github.com/FreeCAD/FreeCAD), commit
# 3160daf1e2b6. See ../../../NOTICE.
"""Draft.clone, which Path.Main.Job uses to put a part into a Job's Model: a Part::FeaturePython named Clone whose shape
is its Objects' shape, with Draft's properties."""
import FreeCAD


class Clone:
    def __init__(self, obj):
        self.Type = "Clone"
        obj.Proxy = self

    def execute(self, obj):
        """draftobjects/clone.py's execute for one 3D object: its shape (Part.getShape), the clone's placement kept."""
        import Part
        pl = obj.Placement
        shapes = [Part.getShape(o) for o in obj.Objects]
        shapes = [s for s in shapes if not s.isNull()]
        if shapes:
            sh = shapes[0] if len(shapes) == 1 else Part.makeCompound(shapes)
            if obj.Scale != FreeCAD.Vector(1, 1, 1):
                op = sh.Placement
                sh.Placement = FreeCAD.Placement()
                m = FreeCAD.Matrix()
                m.m[0][0], m.m[1][1], m.m[2][2] = obj.Scale.x, obj.Scale.y, obj.Scale.z
                sh.transformShape(m, False, True)
                sh.Placement = op
            obj.Shape = sh
        obj.Placement = pl

    def onChanged(self, obj, prop):
        pass

    def dumps(self):
        return None

    def loads(self, state):
        return None

    def __repr__(self):
        return f"<draftobjects.clone.Clone object at {hex(id(self))}>"


def clone(obj, delta=None, forcedraft=False):
    doc = FreeCAD.ActiveDocument
    cl = doc.addObject("Part::FeaturePython", "Clone")
    cl.addProperty("App::PropertyLinkListGlobal", "Objects", "Draft", "The objects included in this clone")
    cl.addProperty("App::PropertyVector", "Scale", "Draft", "The scale factor of this clone")
    cl.addProperty("App::PropertyBool", "Fuse", "Draft", "If Clones includes several objects,\nset True for fusion "
                   "or False for compound")
    cl.addProperty("App::PropertyBool", "ForceCompound", "Draft", "Always create a compound")
    for t, n, g in (("App::PropertyEnumeration", "AttacherEngine", "Attachment"),
                    ("App::PropertyString", "AttacherType", "Attachment"),
                    ("App::PropertyPlacement", "AttachmentOffset", "Attachment"),
                    ("App::PropertyLinkSubList", "AttachmentSupport", "Attachment"),
                    ("App::PropertyEnumeration", "MapMode", "Attachment"),
                    ("App::PropertyFloat", "MapPathParameter", "Attachment"),
                    ("App::PropertyBool", "MapReversed", "Attachment")):
        cl.addProperty(t, n, g, "")
    cl.AttacherEngine = ["Engine 3D", "Engine Plane", "Engine Line", "Engine Point"]
    cl.AttacherType = "Attacher::AttachEngine3D"
    cl.MapMode = ["Deactivated"]
    for n in ("AttacherType",):
        cl.setEditorMode(n, ["ReadOnly", "Hidden"])
    for n in ("AttachmentOffset", "MapPathParameter", "MapReversed"):
        cl.setEditorMode(n, ["Hidden"])
    Clone(cl)
    cl.Objects = [obj]
    cl.Scale = FreeCAD.Vector(1, 1, 1)
    cl.Label = "Clone of " + obj.Label
    cl.Placement = obj.Placement
    return cl
