# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses FreeCAD's ParameterGrp (src/Base/Parameter.cpp, Copyright (c) 2002 Juergen
# Riegel) and keeps FreeCAD's licence, the GNU Lesser General Public License, version 2.1 or (at your option) any later
# version; the text is in ../../ui/LICENSE. FreeCAD (https://github.com/FreeCAD/FreeCAD), commit 3160daf1e2b6.
# See ../../NOTICE.
"""FreeCAD.ParamGet for the CAM workbench's Python: an in-memory parameter tree, empty as a fresh FreeCAD profile is
(every Get* returns the caller's default), with the observers FreeCAD's ParameterGrp notifies."""
from __future__ import annotations


class ParameterGrp:
    def __init__(self, path):
        self._path = path
        self._vals = {}             # (kind, name) -> value
        self._groups = {}
        self._observers = []

    def GetGroup(self, name):
        node = self
        for part in name.split("/"):
            if part:
                node = node._groups.setdefault(part, ParameterGrp(node._path + "/" + part))
        return node

    def GetGroups(self):
        return list(self._groups)

    def HasGroup(self, name):
        return name in self._groups

    def RemGroup(self, name):
        self._groups.pop(name, None)

    def IsEmpty(self):
        return not self._vals and not self._groups

    def _get(self, kind, name, default):
        return self._vals.get((kind, name), default)

    def _set(self, kind, name, value):
        self._vals[(kind, name)] = value
        for o in list(self._observers):
            if hasattr(o, "onChange"):
                o.onChange(self, name)
            elif callable(o):
                o(self, kind, name, value)

    def GetString(self, name, default=""):
        return self._get("String", name, default)

    def SetString(self, name, v):
        self._set("String", name, str(v))

    def GetBool(self, name, default=False):
        return self._get("Bool", name, default)

    def SetBool(self, name, v):
        self._set("Bool", name, bool(v))

    def GetInt(self, name, default=0):
        return self._get("Int", name, default)

    def SetInt(self, name, v):
        self._set("Int", name, int(v))

    def GetUnsigned(self, name, default=0):
        return self._get("Unsigned", name, default)

    def SetUnsigned(self, name, v):
        self._set("Unsigned", name, int(v))

    def GetFloat(self, name, default=0.0):
        return self._get("Float", name, default)

    def SetFloat(self, name, v):
        self._set("Float", name, float(v))

    def _rem(self, kind, name):
        self._vals.pop((kind, name), None)

    def RemString(self, name):
        self._rem("String", name)

    def RemBool(self, name):
        self._rem("Bool", name)

    def RemInt(self, name):
        self._rem("Int", name)

    def RemUnsigned(self, name):
        self._rem("Unsigned", name)

    def RemFloat(self, name):
        self._rem("Float", name)

    def _names(self, kind):
        return [n for k, n in self._vals if k == kind]

    def GetStrings(self):
        return self._names("String")

    def GetBools(self):
        return self._names("Bool")

    def GetInts(self):
        return self._names("Int")

    def GetFloats(self):
        return self._names("Float")

    def GetUnsigneds(self):
        return self._names("Unsigned")

    def GetContents(self):
        return [(k, n, v) for (k, n), v in self._vals.items()]

    def Attach(self, obs):
        self._observers.append(obs)

    def AttachManager(self, obs):
        self._observers.append(obs)

    def Detach(self, obs):
        if obs in self._observers:
            self._observers.remove(obs)

    def Clear(self):
        self._vals.clear()
        self._groups.clear()

    def Notify(self, name):
        pass

    def NotifyAll(self):
        pass

    def Export(self, path):
        pass

    def Import(self, path):
        pass

    def GetGroupName(self):
        return self._path.rsplit("/", 1)[-1]


_ROOTS = {}


def ParamGet(path: str) -> ParameterGrp:
    root, _, rest = path.partition(":")
    node = _ROOTS.setdefault(root, ParameterGrp(root))
    return node.GetGroup(rest)


def reset():
    _ROOTS.clear()
