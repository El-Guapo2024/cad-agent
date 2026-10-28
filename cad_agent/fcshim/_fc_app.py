# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses FreeCAD's App document, document objects and properties and keeps FreeCAD's
# licence, the GNU Lesser General Public License, version 2.1 or (at your option) any later version; the text is in
# ../../ui/LICENSE.
#
#   Derived from: src/App/Document.cpp (Copyright (c) 2002 Juergen Riegel), src/App/DocumentObject.cpp,
#                 src/App/DocumentObjectPyImp.cpp, src/App/PropertyContainerPyImp.cpp (Copyright (c) 2007 Juergen Riegel),
#                 src/App/PropertyStandard.cpp, src/App/PropertyUnits.cpp, src/App/PropertyLinks.cpp,
#                 src/App/PropertyExpressionEngine.cpp (Copyright (c) 2015 Eivind Kvedalen), src/App/FeaturePython.cpp
#                 FreeCAD (https://github.com/FreeCAD/FreeCAD), commit 3160daf1e2b62b0472854da4848255c6b3ad554c
#
# See ../../NOTICE.
"""FreeCAD's App for the CAM workbench's Python: a Document of DocumentObjects whose properties are typed as FreeCAD's
(App::PropertyLength gives a Quantity in mm and clamps at 0, App::PropertyEnumeration takes its list then a choice,
App::PropertyLinkSubList returns [(obj, ('Face1',))] ...), with addProperty, setEditorMode, the ExpressionEngine
(expressions evaluated by cad_agent/fcexpr.py, the page's own engine, at recompute as PropertyExpressionEngine::execute
does) and Document.recompute in dependency order calling each FeaturePython proxy's execute."""
from __future__ import annotations

import re
import sys

from . import _fc_base as B
from . import _fc_units as U

# ─── property types ─────────────────────────────────────────────────────────────────────────────────────────────────

_VELOCITY = U.Velocity
QUANTITY_TYPES = {
    "App::PropertyLength": (U.LENGTH, (0.0, sys.float_info.max)),
    "App::PropertyDistance": (U.LENGTH, None),
    "App::PropertySpeed": (_VELOCITY, None),
    "App::PropertyAngle": (U.ANGLE, (-360.0, 360.0)),
    "App::PropertyArea": (U.Area, (0.0, sys.float_info.max)),
    "App::PropertyVolume": (U.Volume, (0.0, sys.float_info.max)),
    "App::PropertyAcceleration": (U.Acceleration, None),
    "App::PropertyFrequency": (U.Frequency, None),
    "App::PropertyTime": (U.TIME, None),
    "App::PropertyQuantity": (U.Unit(), None),
}
LINK_TYPES = ("App::PropertyLink", "App::PropertyLinkGlobal", "App::PropertyLinkHidden", "App::PropertyLinkChild")
LINKLIST_TYPES = ("App::PropertyLinkList", "App::PropertyLinkListGlobal", "App::PropertyLinkListHidden",
                  "App::PropertyLinkListChild")
LINKSUB_TYPES = ("App::PropertyLinkSub", "App::PropertyLinkSubGlobal", "App::PropertyLinkSubHidden")
LINKSUBLIST_TYPES = ("App::PropertyLinkSubList", "App::PropertyLinkSubListGlobal", "App::PropertyLinkSubListHidden",
                     "App::PropertyXLinkSubList")


class PropertyError(Exception):
    pass


class _Prop:
    __slots__ = ("type", "name", "group", "doc", "value", "modes", "status", "enums", "unit", "limits", "constraint")

    def __init__(self, type_, name, group="", doc="", modes=(), status=()):
        self.type, self.name, self.group, self.doc = type_, name, group, doc
        self.modes = set(modes)
        self.status = set(status)
        self.enums = []
        self.unit, self.limits = QUANTITY_TYPES.get(type_, (None, None))
        self.constraint = None
        self.value = _default(type_)


def _default(t):
    if t in QUANTITY_TYPES:
        return 0.0
    return {
        "App::PropertyBool": False, "App::PropertyInteger": 0, "App::PropertyIntegerConstraint": 0,
        "App::PropertyPercent": 0, "App::PropertyFloat": 0.0, "App::PropertyFloatConstraint": 0.0,
        "App::PropertyPrecision": 0.0, "App::PropertyString": "", "App::PropertyFile": "", "App::PropertyFont": "",
        "App::PropertyEnumeration": None, "App::PropertyStringList": [], "App::PropertyFloatList": [],
        "App::PropertyIntegerList": [], "App::PropertyBoolList": [], "App::PropertyVectorList": [],
        "App::PropertyMap": {}, "App::PropertyPythonObject": None, "App::PropertyPlacement": None,
        "App::PropertyVector": None, "App::PropertyVectorDistance": None, "App::PropertyPosition": None,
        "App::PropertyDirection": None, "App::PropertyColor": (0.0, 0.0, 0.0, 0.0), "App::PropertyUUID": "",
        "Part::PropertyPartShape": None, "Path::PropertyPath": None, "App::PropertyExpressionEngine": None,
        "Materials::PropertyMaterial": None, "App::PropertyMatrix": None,
    }.get(t, [] if t in LINKLIST_TYPES or t in LINKSUBLIST_TYPES else None)


def _is_docobj(v):
    return isinstance(v, DocumentObject)


def _as_float(v, what):
    if isinstance(v, bool):
        return float(v)
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, U.Quantity):
        return v.Value
    raise TypeError(f"{what}: float expected, got {type(v).__name__}")


def _coerce(p: _Prop, v, obj=None):
    """PropertyX::setPyObject: the stored value."""
    t = p.type
    if t in QUANTITY_TYPES:
        if isinstance(v, U.Unit):
            p.unit = v
            return p.value
        if isinstance(v, str):
            q = U.Quantity.parse(v)
        elif isinstance(v, U.Quantity):
            q = v
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            q = U.Quantity(float(v), p.unit)
        else:
            raise TypeError(f"wrong type as quantity: {type(v).__name__}")
        val = q.Value
        if p.limits:
            lo, hi = p.limits
            val = hi if val > hi else (lo if val < lo else val)
        if not q.Unit.isEmpty() and q.Unit != p.unit:
            if t == "App::PropertyQuantity" and p.unit.isEmpty():
                p.unit = q.Unit
            else:
                raise ValueError("Not matching Unit!")
        return float(val)
    if t == "App::PropertyBool":
        if isinstance(v, (bool, int)):
            return bool(v)
        raise TypeError("type must be bool")
    if t in ("App::PropertyInteger", "App::PropertyPercent"):
        if isinstance(v, float) and v.is_integer():
            v = int(v)
        if not isinstance(v, int):
            raise TypeError(f"type must be int, not {type(v).__name__}")
        if t == "App::PropertyPercent" and not 0 <= v <= 100:
            raise ValueError("Out of range")
        return int(v)
    if t == "App::PropertyIntegerConstraint":
        if isinstance(v, (tuple, list)):
            val, lo, hi, step = (list(v) + [None, None, None])[:4]
            p.constraint = (int(lo), int(hi), int(step) if step is not None else 1)
            v = val
        v = int(v)
        if p.constraint:
            lo, hi, _ = p.constraint
            v = hi if v > hi else (lo if v < lo else v)
        return v
    if t == "App::PropertyFloatConstraint":
        if isinstance(v, (tuple, list)):
            val, lo, hi, step = (list(v) + [None, None, None])[:4]
            p.constraint = (float(lo), float(hi), float(step) if step is not None else 1.0)
            v = val
        v = _as_float(v, p.name)
        if p.constraint:
            lo, hi, _ = p.constraint
            v = hi if v > hi else (lo if v < lo else v)
        return v
    if t in ("App::PropertyFloat", "App::PropertyPrecision"):
        return _as_float(v, p.name)
    if t in ("App::PropertyString", "App::PropertyFile", "App::PropertyFont", "App::PropertyUUID"):
        if not isinstance(v, str):
            raise TypeError(f"type must be str, not {type(v).__name__}")
        return v
    if t == "App::PropertyEnumeration":
        if isinstance(v, (list, tuple)):
            p.enums = [str(x) for x in v]
            cur = p.value
            if cur in p.enums:
                return cur
            return p.enums[0] if p.enums else None
        if isinstance(v, int) and not isinstance(v, bool):
            if not 0 <= v < len(p.enums):
                raise ValueError("Out of range")
            return p.enums[v]
        if isinstance(v, str):
            if v not in p.enums:
                raise ValueError(f"'{v}' is not part of the enumeration in {obj.Name if obj else ''}.{p.name}")
            return v
        raise TypeError("Enumeration: str, int or list expected")
    if t == "App::PropertyStringList":
        if isinstance(v, str):
            return [v]
        return [str(x) for x in v]
    if t == "App::PropertyFloatList":
        return [_as_float(x, p.name) for x in v]
    if t in ("App::PropertyIntegerList",):
        return [int(x) for x in v]
    if t == "App::PropertyBoolList":
        return [bool(x) for x in v]
    if t == "App::PropertyVectorList":
        return [B.Vector(x) for x in v]
    if t == "App::PropertyMap":
        return {str(k): str(x) for k, x in dict(v).items()}
    if t in ("App::PropertyVector", "App::PropertyVectorDistance", "App::PropertyPosition", "App::PropertyDirection"):
        return B.Vector(v)
    if t == "App::PropertyPlacement":
        if isinstance(v, B.Matrix):
            return B.Placement(v)
        return B.Placement(v)
    if t in LINK_TYPES:
        if v is None or _is_docobj(v):
            return v
        raise TypeError("type must be 'DocumentObject' or 'NoneType'")
    if t in LINKLIST_TYPES:
        if v is None:
            return []
        if _is_docobj(v):
            return [v]
        out = list(v)
        if not all(_is_docobj(x) for x in out):
            raise TypeError("type must be 'DocumentObject', list of 'DocumentObject', or NoneType")
        return out
    if t in LINKSUB_TYPES:
        return _linksub(v)
    if t in LINKSUBLIST_TYPES:
        return _linksublist(v)
    if t == "Part::PropertyPartShape":
        import Part
        if v is None:
            return Part.Shape()
        if not isinstance(v, Part.Shape):
            raise TypeError("type must be 'Shape'")
        return v.copy() if hasattr(v, "copy") else v
    if t == "Path::PropertyPath":
        import PathApp
        if not isinstance(v, PathApp.Path):
            raise TypeError("type must be 'Path'")
        return PathApp.Path(v)
    return v


def _linksub(v):
    if v is None:
        return None
    if _is_docobj(v):
        return (v, [])
    if isinstance(v, (tuple, list)):
        if not v:
            return None
        if len(v) != 2:
            raise ValueError("Expect input sequence of size 2")
        o, s = v
        if o is not None and not _is_docobj(o):
            raise TypeError("type of first element in tuple must be 'DocumentObject' or 'NoneType'")
        if isinstance(s, str):
            return (o, [s]) if o is not None else None
        return (o, [str(x) for x in s]) if o is not None else None
    raise TypeError("Expects a DocumentObject or a (DocumentObject, sub) pair")


def _linksublist(v):
    """[(obj, sub), ...] flattened: PropertyLinkSubList::setPyObject's three syntaxes."""
    if v is None:
        return []
    if _is_docobj(v):
        return [(v, "")]
    if isinstance(v, (tuple, list)) and len(v) == 2 and _is_docobj(v[0]) and (isinstance(v[1], str) or (
            isinstance(v[1], (list, tuple)) and all(isinstance(x, str) for x in v[1]))):
        subs = [v[1]] if isinstance(v[1], str) else list(v[1])
        return [(v[0], s) for s in subs] if subs else [(v[0], "")]
    out = []
    for item in v:
        if isinstance(item, (tuple, list)) and len(item) == 2 and _is_docobj(item[0]):
            o, s = item
            if isinstance(s, str):
                out.append((o, s))
            else:
                for x in s:
                    if not isinstance(x, str):
                        raise TypeError("Expects sequence of items of type DocObj, (DocObj,SubName), or (DocObj, (SubName,...))")
                    out.append((o, x))
        elif _is_docobj(item):
            out.append((item, ""))
        else:
            raise TypeError("Expects sequence of items of type DocObj, (DocObj,SubName), or (DocObj, (SubName,...))")
    return out


def _get(p: _Prop):
    """PropertyX::getPyObject."""
    t, v = p.type, p.value
    if t in QUANTITY_TYPES:
        return U.Quantity(v, p.unit)
    if t in ("App::PropertyStringList", "App::PropertyFloatList", "App::PropertyIntegerList", "App::PropertyBoolList"):
        return list(v)
    if t == "App::PropertyVectorList":
        return [B.Vector(x) for x in v]
    if t == "App::PropertyMap":
        return dict(v)
    if t in ("App::PropertyVector", "App::PropertyVectorDistance", "App::PropertyPosition", "App::PropertyDirection"):
        return B.Vector(v) if v is not None else B.Vector()
    if t == "App::PropertyPlacement":
        return B.Placement(v) if v is not None else B.Placement()
    if t in LINKLIST_TYPES:
        return list(v)
    if t in LINKSUB_TYPES:
        if v is None:
            return None
        return (v[0], list(v[1]))
    if t in LINKSUBLIST_TYPES:
        groups = []
        for o, s in v:
            if not groups or groups[-1][0] is not o:
                groups.append((o, []))
            groups[-1][1].append(s)
        return [(o, tuple(s)) for o, s in groups]
    if t == "Part::PropertyPartShape":
        import Part
        if v is None:
            return Part.Shape()
        return v.copy() if hasattr(v, "copy") else v
    if t == "Path::PropertyPath":
        import PathApp
        return PathApp.Path(v) if v is not None else PathApp.Path()
    return v


def links_of(p: _Prop):
    t, v = p.type, p.value
    if t in LINK_TYPES:
        return [v] if v is not None else []
    if t in LINKLIST_TYPES:
        return list(v)
    if t in LINKSUB_TYPES:
        return [v[0]] if v else []
    if t in LINKSUBLIST_TYPES:
        return [o for o, _ in v]
    return []


# ─── type system ────────────────────────────────────────────────────────────────────────────────────────────────────

BASES = {
    "App::DocumentObject": [],
    "App::GeoFeature": ["App::DocumentObject"],
    "App::FeaturePython": ["App::DocumentObject"],
    "App::DocumentObjectGroup": ["App::DocumentObject"],
    "App::DocumentObjectGroupPython": ["App::DocumentObjectGroup"],
    "Part::Feature": ["App::GeoFeature"],
    "Part::FeaturePython": ["Part::Feature"],
    "Part::Primitive": ["Part::Feature"],
    "Part::Box": ["Part::Primitive"],
    "Part::Cylinder": ["Part::Primitive"],
    "Part::Cone": ["Part::Primitive"],
    "Part::Sphere": ["Part::Primitive"],
    "Part::LocalCoordinateSystem": ["App::GeoFeature"],
    "Path::Feature": ["App::GeoFeature"],
    "Path::FeaturePython": ["Path::Feature"],
    "Path::FeatureCompound": ["Path::Feature"],
    "Path::FeatureCompoundPython": ["Path::FeatureCompound"],
    "PartDesign::Body": ["Part::Feature"],
    "Spreadsheet::Sheet": ["App::DocumentObject"],
}


def derived_from(type_id, base):
    if type_id == base:
        return True
    return any(derived_from(b, base) for b in BASES.get(type_id, []))


def _base_props(type_id):
    """The C++ properties an object of a type has, in FreeCAD's groups."""
    out = [("App::PropertyString", "Label", "Base", "User name of the object (UTF8)", (), ()),
           ("App::PropertyString", "Label2", "Base", "User description of the object (UTF8)", ("Hidden",), ()),
           ("App::PropertyExpressionEngine", "ExpressionEngine", "Base", "Property expressions", ("Hidden",), ()),
           ("App::PropertyBool", "Visibility", "", "Whether the object is visible", ("Hidden",), ())]
    if derived_from(type_id, "App::GeoFeature"):
        out.append(("App::PropertyPlacement", "Placement", "", "Object placement", (), ()))
    if derived_from(type_id, "Part::Feature"):
        out.append(("Part::PropertyPartShape", "Shape", "", "Shape of the object", (), ()))
    if derived_from(type_id, "Path::Feature"):
        out.append(("Path::PropertyPath", "Path", "Base", "The path data of this feature", (), ()))
    if derived_from(type_id, "App::DocumentObjectGroup"):
        out.append(("App::PropertyLinkList", "Group", "Base", "List of referenced objects", (), ()))
    if type_id.endswith("Python"):
        out.append(("App::PropertyPythonObject", "Proxy", "", "", (), ()))
    return out


_PRIMITIVE_PROPS = {
    "Part::Box": [("App::PropertyLength", "Length", "Box", 10.0), ("App::PropertyLength", "Width", "Box", 10.0),
                  ("App::PropertyLength", "Height", "Box", 10.0)],
    "Part::Cylinder": [("App::PropertyLength", "Radius", "Cylinder", 2.0),
                       ("App::PropertyLength", "Height", "Cylinder", 10.0),
                       ("App::PropertyAngle", "Angle", "Cylinder", 360.0)],
    "Part::Cone": [("App::PropertyLength", "Radius1", "Cone", 2.0), ("App::PropertyLength", "Radius2", "Cone", 4.0),
                   ("App::PropertyLength", "Height", "Cone", 10.0), ("App::PropertyAngle", "Angle", "Cone", 360.0)],
    "Part::Sphere": [("App::PropertyLength", "Radius", "Sphere", 5.0)],
}


# ─── document objects ───────────────────────────────────────────────────────────────────────────────────────────────

_OWN = {"_props", "_doc", "Name", "TypeId", "_touched", "_exprs", "_ext", "_removed", "ViewObject", "_status",
        "__dict__", "_in_change"}


class DocumentObject:
    def __init__(self, doc, type_id, name):
        o = object.__setattr__
        o(self, "_props", {})
        o(self, "_doc", doc)
        o(self, "Name", name)
        o(self, "TypeId", type_id)
        o(self, "_touched", True)
        o(self, "_exprs", {})
        o(self, "_ext", [])
        o(self, "_removed", False)
        o(self, "ViewObject", None)
        o(self, "_status", set())
        o(self, "_in_change", False)
        for t, n, g, d, modes, status in _base_props(type_id):
            self._props[n] = _Prop(t, n, g, d, modes, status)
        for t, n, g, dflt in _PRIMITIVE_PROPS.get(type_id, []):
            p = _Prop(t, n, g, "")
            p.value = dflt
            self._props[n] = p
        self._props["Label"].value = name
        self._props["Visibility"].value = True

    # ── attribute access: properties first ──
    def __getattr__(self, name):
        props = object.__getattribute__(self, "_props")
        if name in props:
            return _get(props[name])
        proxy = props.get("Proxy")
        raise AttributeError(f"'{self.TypeId}' object has no attribute '{name}'")

    def __setattr__(self, name, value):
        if name in _OWN:
            object.__setattr__(self, name, value)
            return
        props = self._props
        if name not in props:
            # Python attributes on a document object are not allowed in FreeCAD; CAM sets none but the proxy's
            raise AttributeError(f"Object attribute '{name}' is not found or not a property")
        p = props[name]
        if "ReadOnly" in p.status and name not in ("Proxy",):
            pass
        old = p.value
        p.value = _coerce(p, value, self)
        if name == "Proxy":
            self._touched = True
            self._on_changed(name)
            return
        if name not in ("Label2", "Visibility") and "Output" not in p.status:
            self._touched = True
        self._on_changed(name)

    def _on_changed(self, name):
        if name == "Label":
            self._doc._unique_label(self)
        proxy = self._props.get("Proxy")
        px = proxy.value if proxy is not None else None
        if px is not None and hasattr(px, "onChanged") and not self._doc._restoring:
            px.onChanged(self, name)
        if name == "Group" and derived_from(self.TypeId, "App::DocumentObjectGroup") or (name == "Group" and self._ext):
            pass

    def __repr__(self):
        px = self._props.get("Proxy")
        if px is not None and px.value is not None:
            return f"<{self.TypeId} ({px.value!r})>"
        return f"<{self.TypeId} object>"

    def __eq__(self, o):
        return self is o

    def __hash__(self):
        return id(self)

    # ── PropertyContainerPy ──
    def addProperty(self, type_, name, group="", doc="", attr=0, read_only=False, hidden=False, locked=False,
                    enum_vals=None):
        if name in self._props:
            raise PropertyError(f"Object already has a property {name}")
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", name):
            raise ValueError(f"Invalid property name '{name}'")
        modes = set()
        if read_only:
            modes.add("ReadOnly")
        if hidden:
            modes.add("Hidden")
        p = _Prop(type_, name, group, doc, modes, {"Dynamic"})
        self._props[name] = p
        if enum_vals is not None and type_ == "App::PropertyEnumeration":
            p.enums = list(enum_vals)
            p.value = p.enums[0] if p.enums else None
        return self

    def removeProperty(self, name):
        p = self._props.get(name)
        if p is None or "Dynamic" not in p.status:
            return False
        del self._props[name]
        self._exprs.pop(name, None)
        return True

    @property
    def PropertiesList(self):
        return sorted(self._props)

    def getPropertyByName(self, name, checkOwner=0):
        if name not in self._props:
            raise AttributeError(f"Property container has no property '{name}'")
        return _get(self._props[name])

    def getTypeIdOfProperty(self, name):
        return self._props[name].type

    def getGroupOfProperty(self, name):
        return self._props[name].group

    def setGroupOfProperty(self, name, group):
        self._props[name].group = group

    def getDocumentationOfProperty(self, name):
        return self._props[name].doc

    def setDocumentationOfProperty(self, name, doc):
        self._props[name].doc = doc

    def getEnumerationsOfProperty(self, name):
        p = self._props[name]
        return list(p.enums) if p.type == "App::PropertyEnumeration" else None

    def getEditorMode(self, name):
        p = self._props[name]
        return [m for m in ("ReadOnly", "Hidden") if m in p.modes]

    def setEditorMode(self, name, mode):
        p = self._props.get(name)
        if p is None:
            return
        if isinstance(mode, int):
            p.modes = {m for m, b in (("ReadOnly", 1), ("Hidden", 2)) if mode & b}
        else:
            p.modes = set(mode)

    def setPropertyStatus(self, name, status):
        p = self._props[name]
        for s in ([status] if isinstance(status, str) else status):
            if s.startswith("-"):
                p.status.discard(s[1:])
            else:
                p.status.add(s)

    def getPropertyStatus(self, name=""):
        return sorted(self._props[name].status) if name else []

    # ── DocumentObjectPy ──
    @property
    def Document(self):
        return self._doc

    @property
    def FullName(self):
        return f"{self._doc.Name}#{self.Name}"

    @property
    def State(self):
        out = []
        if self._touched:
            out.append("Touched")
        if "Invalid" in self._status:
            out.append("Invalid")
        return out

    @property
    def InList(self):
        return [o for o in self._doc.Objects if o is not self and self in o.OutList]

    @property
    def OutList(self):
        out = []
        for p in self._props.values():
            for x in links_of(p):
                if x is not None and x not in out:
                    out.append(x)
        for o in self._expr_deps():
            if o not in out and o is not self:
                out.append(o)
        return out

    @property
    def OutListRecursive(self):
        seen, todo = [], list(self.OutList)
        while todo:
            x = todo.pop(0)
            if x in seen:
                continue
            seen.append(x)
            todo.extend(x.OutList)
        return seen

    @property
    def InListRecursive(self):
        seen, todo = [], list(self.InList)
        while todo:
            x = todo.pop(0)
            if x in seen:
                continue
            seen.append(x)
            todo.extend(x.InList)
        return seen

    def isDerivedFrom(self, type_id):
        return derived_from(self.TypeId, type_id)

    def addExtension(self, name, proxy=None):
        self._ext.append(name)
        if "GroupExtension" in name and "Group" not in self._props:
            self._props["Group"] = _Prop("App::PropertyLinkList", "Group", "Base", "List of referenced objects")
            self._props["_GroupTouched"] = _Prop("App::PropertyBool", "_GroupTouched", "Base", "", ("Hidden",))

    def hasExtension(self, name, derived=True):
        if name in self._ext:
            return True
        if derived and "GroupExtension" in name:
            return any("GroupExtension" in e for e in self._ext) or derived_from(self.TypeId, "App::DocumentObjectGroup")
        return False

    def touch(self, prop=None):
        self._touched = True

    def purgeTouched(self):
        self._touched = False

    def isTouched(self):
        return self._touched

    def recompute(self, recursive=False):
        self._doc._execute(self)
        return True

    def isValid(self):
        return "Invalid" not in self._status

    def getStatusString(self):
        """DocumentObject::getStatusString: the error's text, else "Touched" or "Valid"."""
        for st in self._status:
            if st.startswith("Error:"):
                return st[len("Error:"):]
        return "Touched" if self._touched else "Valid"

    def getParentGroup(self):
        for o in self._doc.Objects:
            if "Group" in o._props and self in o._props["Group"].value:
                return o
        return None

    def getSubObject(self, sub, retType=0, matrix=None, transform=True, depth=0):
        shape = self.Shape
        if not sub:
            return shape
        return shape.getElement(sub)

    def getLinkedObject(self, *a, **k):
        return self

    @property
    def Content(self):
        return ""

    @property
    def Module(self):
        return self.TypeId.split("::")[0]

    # ── groups (App::GroupExtension) ──
    def addObject(self, obj):
        g = self._props["Group"]
        if obj not in g.value:
            # an object is in one group only (GroupExtension::addObjects)
            for o in self._doc.Objects:
                if o is not self and "Group" in o._props and obj in o._props["Group"].value:
                    o._props["Group"].value.remove(obj)
            g.value = g.value + [obj]
            self._touched = True
            self._on_changed("Group")
        return [obj]

    def addObjects(self, objs):
        for o in objs:
            self.addObject(o)
        return list(objs)

    def removeObject(self, obj):
        g = self._props["Group"]
        if obj in g.value:
            g.value = [x for x in g.value if x is not obj]
            self._on_changed("Group")
        return [obj]

    def hasObject(self, obj, recursive=False):
        return obj in self._props["Group"].value

    def newObject(self, type_, name):
        o = self._doc.addObject(type_, name)
        self.addObject(o)
        return o

    # ── expressions ──
    def setExpression(self, path, expr, comment=None):
        path = str(path)
        name = path.lstrip(".").split(".")[0]
        if expr is None or expr == "":
            self._exprs.pop(path, None)
        else:
            self._exprs[path] = str(expr)
        self._touched = True

    @property
    def ExpressionEngine(self):
        return [(k, v) for k, v in sorted(self._exprs.items())]

    def evalExpression(self, expr):
        return self._doc._eval(self, expr)

    def _expr_deps(self):
        out = []
        for e in self._exprs.values():
            for o in self._doc._expr_objects(self, e):
                if o not in out:
                    out.append(o)
        return out

    def supportedProperties(self):
        return sorted(set(QUANTITY_TYPES) | {"App::PropertyBool", "App::PropertyString", "App::PropertyFloat"})


class FeaturePython(DocumentObject):
    pass


# ─── the document ───────────────────────────────────────────────────────────────────────────────────────────────────

def sanitize_name(name: str) -> str:
    """Base::Tools::getIdentifier: the object's internal name made of letters, digits and '_'."""
    if not name:
        return "Unnamed"
    s = re.sub(r"[^A-Za-z0-9_]", "_", name)
    if s[0].isdigit():
        s = "_" + s
    return s


def unique_name(base: str, taken) -> str:
    """Document::getUniqueObjectName: the name itself, else its stem (trailing digits removed) and the next number
    after the highest one in use, written with at least three digits."""
    if base not in taken:
        return base
    stem = re.sub(r"\d+$", "", base)
    best = 0
    for t in taken:
        m = re.fullmatch(re.escape(stem) + r"(\d+)", t)
        if m:
            best = max(best, int(m.group(1)))
    return f"{stem}{best + 1:03d}"


class Document:
    def __init__(self, name="Unnamed", label=None):
        self.Name = name
        self.Label = label or name
        self._objects = []
        self._restoring = False
        self.FileName = ""
        self.Transacting = False
        self.ActiveObject = None
        self.RecomputesFrozen = False
        self.Tip = None
        self._transactions = []
        self.Hidden = False
        self._errors = []

    @property
    def Objects(self):
        return list(self._objects)

    def addObject(self, type_, name=None, *args, **kw):
        if isinstance(type_, str) and type_.startswith("Part::") and type_ not in BASES and type_ != "Part::Feature":
            pass
        base = sanitize_name(name or type_.split("::")[-1])
        nm = unique_name(base, {o.Name for o in self._objects})
        cls = FeaturePython if type_.endswith("Python") else DocumentObject
        o = cls(self, type_, nm)
        self._objects.append(o)
        self._unique_label(o)
        self.ActiveObject = o
        if type_ in ("Part::Box", "Part::Cylinder", "Part::Cone", "Part::Sphere"):
            pass
        return o

    def _unique_label(self, obj):
        lab = obj._props["Label"].value
        others = {o._props["Label"].value for o in self._objects if o is not obj}
        if lab in others:
            obj._props["Label"].value = unique_name(lab, others)

    def getObject(self, name):
        for o in self._objects:
            if o.Name == name:
                return o
        return None

    def getObjectsByLabel(self, label):
        return [o for o in self._objects if o.Label == label]

    def removeObject(self, name):
        o = self.getObject(name) if isinstance(name, str) else name
        if o is None:
            return
        px = o._props.get("Proxy")
        if px is not None and px.value is not None and hasattr(px.value, "onDelete"):
            pass
        for x in self._objects:
            for p in x._props.values():
                if p.type in LINK_TYPES and p.value is o:
                    p.value = None
                elif p.type in LINKLIST_TYPES and o in p.value:
                    p.value = [y for y in p.value if y is not o]
                elif p.type in LINKSUBLIST_TYPES and any(y is o for y, _ in p.value):
                    p.value = [(y, s) for y, s in p.value if y is not o]
                elif p.type in LINKSUB_TYPES and p.value and p.value[0] is o:
                    p.value = None
        self._objects = [x for x in self._objects if x is not o]
        o._removed = True

    def copyObject(self, obj, recursive=False, *a):
        c = self.addObject(obj.TypeId, obj.Name)
        for n, p in obj._props.items():
            if n in ("Label",):
                continue
            if n not in c._props:
                c._props[n] = _Prop(p.type, p.name, p.group, p.doc, p.modes, p.status)
            c._props[n].value = p.value
            c._props[n].enums = list(p.enums)
        c.Label = obj.Label
        return c

    def openTransaction(self, name=""):
        self._transactions.append(name)

    def commitTransaction(self):
        pass

    def abortTransaction(self):
        pass

    def getTempFileName(self, name):
        import tempfile
        return tempfile.mktemp(prefix=name)

    # ── recompute ──
    def _order(self, objs):
        """Dependencies first, in document order where nothing orders them (a depth first walk of the OutList)."""
        out, state = [], {}

        def visit(o):
            s = state.get(id(o))
            if s == 2:
                return
            if s == 1:
                raise RuntimeError("The graph must be a DAG.")
            state[id(o)] = 1
            for d in o.OutList:
                if d in objs:
                    visit(d)
            state[id(o)] = 2
            out.append(o)
        for o in objs:
            visit(o)
        return out

    def recompute(self, objs=None, force=False, checkCycle=False):
        if self.RecomputesFrozen:
            return 0
        touched = [o for o in self._objects if o._touched or force]
        need = set(id(o) for o in touched)
        changed = True
        while changed:                          # and everything that depends on them
            changed = False
            for o in self._objects:
                if id(o) not in need and any(id(d) in need for d in o.OutList):
                    need.add(id(o))
                    changed = True
        todo = [o for o in self._objects if id(o) in need]
        n = 0
        for o in self._order(todo):
            if o._removed:
                continue
            self._execute(o)
            n += 1
        return n

    def _execute(self, o):
        """Document::_recomputeFeature: the expressions, then the proxy's execute, unless it is the proxy's execute
        that asked (FC_PY_CALL_CHECK: a FeaturePython's execute does not run inside itself; obj.recompute() from an
        op's execute only re-evaluates the expressions)."""
        self._apply_expressions(o)
        px = o._props.get("Proxy")
        proxy = px.value if px is not None else None
        if o._in_change:
            return
        object.__setattr__(o, "_in_change", True)
        try:
            for st in [x for x in o._status if x.startswith("Error:")]:
                o._status.discard(st)
            if proxy is not None and hasattr(proxy, "execute"):
                proxy.execute(o)
            elif o.TypeId in ("Part::Box", "Part::Cylinder", "Part::Cone", "Part::Sphere"):
                _execute_primitive(o)
            o._status.discard("Invalid")
        except Exception as e:  # noqa: BLE001 - DocumentObject::recompute marks the object invalid and goes on
            o._status.add("Invalid")
            o._status.add("Error:" + str(e))
            import traceback
            self._errors.append((o.Name, e, traceback.format_exc()))
        finally:
            object.__setattr__(o, "_in_change", False)
        o._touched = False

    # ── expressions (PropertyExpressionEngine::execute) ──
    def _expr_objects(self, owner, text):
        names = set(re.findall(r"(?<![\w.])([A-Za-z_][A-Za-z0-9_]*)\s*\.", text))
        names |= set(re.findall(r"<<([^>]+)>>", text))
        out = []
        for n in names:
            o = self.getObject(n) or next(iter(self.getObjectsByLabel(n)), None)
            if o is not None and o is not owner:
                out.append(o)
        return out

    def _apply_expressions(self, o):
        for path, text in sorted(o._exprs.items()):
            name = path.lstrip(".")
            if name not in o._props:
                continue
            try:
                v = self._eval(o, text)
            except Exception as e:  # noqa: BLE001 - an expression error leaves the value
                o._status.add("Expression:" + str(e))
                continue
            p = o._props[name]
            try:
                p.value = _coerce(p, _from_expr(v, p), o)
            except Exception:  # noqa: BLE001
                continue

    def _eval(self, owner, text):
        from cad_agent import fcexpr as X

        def to_x(v):
            if isinstance(v, U.Quantity):
                return X.Quantity(v.Value, v.Unit.sig)
            if isinstance(v, B.Vector):
                return X.Vector(v.x, v.y, v.z)
            if isinstance(v, (bool, int, float, str)) or v is None:
                return v
            return X.Other(type(v).__name__, repr(v))

        class Vars(dict):
            pass

        vars_ = {}
        for n, p in owner._props.items():
            if p.type in QUANTITY_TYPES or p.type in ("App::PropertyFloat", "App::PropertyInteger", "App::PropertyBool",
                                                      "App::PropertyString", "App::PropertyPercent",
                                                      "App::PropertyIntegerConstraint", "App::PropertyFloatConstraint",
                                                      "App::PropertyEnumeration", "App::PropertyPrecision"):
                vars_[n] = to_x(_get(p))

        def resolve(path):
            ref = path.obj.name if path.obj is not None else (path.names[0] if path.names else None)
            o = self.getObject(ref) or next(iter(self.getObjectsByLabel(ref)), None)
            names = list(path.names) if path.obj is not None else list(path.names[1:])
            if o is None:
                raise X.ExprError(f"Unknown object '{ref}'", "NameError")
            if not names:
                raise X.ExprError("Invalid property", "ExpressionError")
            v = getattr(o, names[0])
            return to_x(v), names[1:]

        env = X.Env(vars_, owner=owner.Name, doc=self.Name, resolve=resolve)
        r = X.evaluate(X.parse(text, frozenset(vars_), owner.Name), env)
        if isinstance(r, X.Quantity):
            return U.Quantity(r.value, U.Unit(*r.dims))
        if isinstance(r, X.Vector):
            return B.Vector(r.x, r.y, r.z)
        return r


def _from_expr(v, p):
    if p.type in QUANTITY_TYPES and isinstance(v, U.Quantity) and v.Unit.isEmpty():
        return v.Value
    if p.type in ("App::PropertyInteger", "App::PropertyIntegerConstraint", "App::PropertyPercent") and isinstance(
            v, (float, U.Quantity)):
        return int(round(float(v)))
    if p.type in ("App::PropertyFloat", "App::PropertyFloatConstraint", "App::PropertyPrecision") and isinstance(
            v, U.Quantity):
        return v.Value
    return v


def _execute_primitive(o):
    import Part
    t = o.TypeId
    if t == "Part::Box":
        s = Part.makeBox(o.Length.Value, o.Width.Value, o.Height.Value)
    elif t == "Part::Cylinder":
        s = Part.makeCylinder(o.Radius.Value, o.Height.Value, B.Vector(), B.Vector(0, 0, 1), o.Angle.Value)
    elif t == "Part::Cone":
        s = Part.makeCone(o.Radius1.Value, o.Radius2.Value, o.Height.Value, B.Vector(), B.Vector(0, 0, 1), o.Angle.Value)
    else:
        s = Part.makeSphere(o.Radius.Value)
    s.Placement = o.Placement
    o._props["Shape"].value = s
