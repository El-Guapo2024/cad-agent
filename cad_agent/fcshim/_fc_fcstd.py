# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It reads FreeCAD's document format as src/App/Document.cpp (Document::Restore) and the
# properties' Restore methods (src/App/PropertyStandard.cpp, PropertyUnits.cpp, PropertyLinks.cpp,
# PropertyGeo.cpp, src/Mod/Part/App/PropertyTopoShape.cpp) write it, and keeps FreeCAD's licence, the GNU Lesser
# General Public License, version 2.1 or (at your option) any later version; the text is in ../../ui/LICENSE.
# FreeCAD (https://github.com/FreeCAD/FreeCAD), commit 3160daf1e2b6. See ../../NOTICE.
"""FreeCAD.openDocument for the CAM tool bit shapes (Mod/CAM/Tools/Shape/*.fcstd): the objects of Document.xml with
their saved property values (strings, numbers, quantities, links, placements, enumerations) and the shapes saved as
BREP files beside it. Nothing is recomputed: a PartDesign Body keeps the shape it was saved with."""
from __future__ import annotations

import io
import xml.etree.ElementTree as ET
import zipfile

from . import _fc_app as A


class _quiet_stdout:
    """The C library's stdout sent to /dev/null for a moment (OCCT writes its notes there, not through Python)."""

    def __enter__(self):
        import os
        import sys
        sys.stdout.flush()
        self._saved = os.dup(1)
        self._null = os.open(os.devnull, os.O_WRONLY)
        os.dup2(self._null, 1)

    def __exit__(self, *a):
        import ctypes
        import os
        try:
            ctypes.CDLL(None).fflush(None)     # what OCCT wrote is still in the C library's buffer
        except (OSError, AttributeError):
            pass
        os.dup2(self._saved, 1)
        os.close(self._saved)
        os.close(self._null)


def load(doc, path):
    with zipfile.ZipFile(path) as zf:
        root = ET.fromstring(zf.read("Document.xml"))
        objs = {}
        objects = root.find("Objects")
        for o in (objects if objects is not None else []):
            if o.tag != "Object":
                continue
            t, name = o.get("type"), o.get("name")
            obj = A.DocumentObject(doc, t, name)
            doc._objects.append(obj)
            objs[name] = obj
        data = root.find("ObjectData")
        pending = []
        for od in (data if data is not None else []):
            obj = objs.get(od.get("name"))
            if obj is None:
                continue
            props = od.find("Properties")
            for p in (props if props is not None else []):
                if p.tag != "Property":
                    continue
                pending.append((obj, p))
        for obj, p in pending:
            _restore(obj, p, objs, zf)
        for o in doc._objects:
            o._touched = False
    return doc


def _restore(obj, p, objs, zf):
    name, t = p.get("name"), p.get("type")
    if name in ("ExpressionEngine", "Proxy"):
        return
    prop = obj._props.get(name)
    if prop is None:
        prop = A._Prop(t, name, p.get("group") or "", p.get("doc") or "", (), {"Dynamic"})
        if p.get("hide") == "1":
            prop.modes.add("Hidden")
        if p.get("ro") == "1":
            prop.modes.add("ReadOnly")
        obj._props[name] = prop
    child = next(iter(p), None)
    if child is None:
        return
    tag = child.tag
    try:
        if tag == "String":
            prop.value = child.get("value", "")
        elif tag == "Float":
            prop.value = float(child.get("value"))
        elif tag == "Integer":
            v = int(child.get("value"))
            if t == "App::PropertyEnumeration":
                lst = p.find("CustomEnumList")
                prop.enums = [e.get("value") for e in lst] if lst is not None else []
                prop.value = prop.enums[v] if 0 <= v < len(prop.enums) else None
            else:
                prop.value = v
        elif tag == "Bool":
            prop.value = child.get("value") == "true"
        elif tag == "Link":
            prop.value = objs.get(child.get("value"))
        elif tag == "LinkList":
            prop.value = [objs[x.get("value")] for x in child if x.get("value") in objs]
        elif tag == "PropertyPlacement":
            from ._fc_base import Placement, Rotation, Vector
            pl = Placement(Vector(float(child.get("Px")), float(child.get("Py")), float(child.get("Pz"))),
                           Rotation(float(child.get("Q0")), float(child.get("Q1")), float(child.get("Q2")),
                                    float(child.get("Q3"))))
            prop.value = pl
        elif tag == "Part" and child.get("file"):
            import Part
            data = zf.read(child.get("file"))
            s = Part.Shape()
            with _quiet_stdout():          # OCCT prints "File was not written with this version of the topology"
                s.importBrepFromString(data.decode("latin-1"))
            prop.value = Part.wrap(s._s) if hasattr(Part, "wrap") else s
    except (KeyError, ValueError, TypeError):
        pass
