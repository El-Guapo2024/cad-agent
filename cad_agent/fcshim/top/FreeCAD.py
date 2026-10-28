# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses FreeCAD's App module as its Python sees it (src/App/ApplicationPy.cpp,
# Copyright (c) 2002 Juergen Riegel) and keeps FreeCAD's licence, the GNU Lesser General Public License, version 2.1 or
# (at your option) any later version; the text is in ../../../ui/LICENSE. FreeCAD
# (https://github.com/FreeCAD/FreeCAD), commit 3160daf1e2b6. See ../../../NOTICE.
"""The `FreeCAD` module that FreeCAD's CAM Python imports, here: Base's types, Units, Console, ParamGet, the documents
and the application's directories (the vendored Mod/CAM under cad_agent/fccam as the home, a per-run folder as the
user's data). GuiUp is False: the CAM code takes its headless paths."""
from __future__ import annotations

import os
import sys
import tempfile
import types
from pathlib import Path as _Path

from cad_agent.fcshim import _fc_app as _app
from cad_agent.fcshim import _fc_base as _base
from cad_agent.fcshim import _fc_params as _params
from cad_agent.fcshim import _fc_units as Units  # noqa: N812

Vector = _base.Vector
Rotation = _base.Rotation
Placement = _base.Placement
Matrix = _base.Matrix
BoundBox = _base.BoundBox
Document = _app.Document
DocumentObject = _app.DocumentObject
DocumentObjectGroup = _app.DocumentObject
GeoFeature = _app.DocumentObject
ParamGet = _params.ParamGet
GuiUp = False

Base = types.ModuleType("FreeCAD.Base")
Base.Vector = Vector
Base.Rotation = Rotation
Base.Placement = Placement
Base.Matrix = Matrix
Base.BoundBox = BoundBox
Base.Precision = _base.Precision
Base.FreeCADError = _base.FreeCADError
Base.Quantity = Units.Quantity
Base.Unit = Units.Unit
Base.CADKernelError = RuntimeError
Base.ValueError = ValueError
sys.modules.setdefault("FreeCAD.Base", Base)

HOME = str(_Path(__file__).resolve().parents[2] / "fccam") + os.sep


class _Console:
    """Base::Console: messages go to the run's log (cad_agent/cam_doc.py reads it), errors to stderr when asked."""

    def __init__(self):
        self.log = []
        self.echo = bool(os.environ.get("CAD_CAM_ECHO"))

    def _put(self, kind, msg):
        self.log.append((kind, str(msg)))
        if self.echo:
            sys.stderr.write(f"[{kind}] {msg}")

    def PrintMessage(self, msg):
        self._put("Msg", msg)

    def PrintLog(self, msg):
        self._put("Log", msg)

    def PrintWarning(self, msg):
        self._put("Wrn", msg)

    def PrintError(self, msg):
        self._put("Err", msg)

    def PrintUserWarning(self, notifier, msg):
        self._put("Wrn", msg)

    def PrintUserError(self, notifier, msg):
        self._put("Err", msg)

    def PrintCritical(self, msg):
        self._put("Critical", msg)

    def PrintNotification(self, msg):
        self._put("Notification", msg)

    def PrintDeveloperWarning(self, notifier, msg):
        self._put("Wrn", msg)


Console = _Console()


class _Qt:
    @staticmethod
    def translate(context, text, *a):
        return text

    @staticmethod
    def QT_TRANSLATE_NOOP(context, text):
        return text


Qt = _Qt()

_documents = {}
ActiveDocument = None
_user_dir = None


def _set_active(doc):
    global ActiveDocument
    ActiveDocument = doc
    sys.modules[__name__].ActiveDocument = doc


def newDocument(name="Unnamed", label=None, hidden=False, temp=False):
    n = _app.unique_name(_app.sanitize_name(name), set(_documents))
    d = Document(n, label or n)
    d.Hidden = hidden
    _documents[n] = d
    if not hidden:
        _set_active(d)
    return d


def getDocument(name):
    if name not in _documents:
        raise NameError(f"Unknown document '{name}'")
    return _documents[name]


def setActiveDocument(name):
    _set_active(_documents.get(name))


def closeDocument(name):
    d = _documents.pop(name, None)
    if d is not None and ActiveDocument is d:
        _set_active(next(iter(_documents.values()), None))


def listDocuments():
    return dict(_documents)


def openDocument(path, hidden=False):
    from cad_agent.fcshim import _fc_fcstd
    d = newDocument(_Path(path).stem, hidden=True)
    _fc_fcstd.load(d, path)
    d.FileName = str(path)
    if not hidden:
        _set_active(d)
    return d


def getHomePath():
    return HOME


def getResourceDir():
    return HOME


def getUserAppDataDir():
    global _user_dir
    if _user_dir is None:
        base = os.environ.get("CAD_CAM_USER_DIR")
        _user_dir = base or tempfile.mkdtemp(prefix="cad-cam-user-")
    return _user_dir.rstrip(os.sep) + os.sep


def getUserConfigDir():
    return getUserAppDataDir()


def getUserMacroDir(actual=False):
    d = os.path.join(getUserAppDataDir(), "Macro")
    os.makedirs(d, exist_ok=True)
    return d


def getUserCachePath():
    return getUserAppDataDir()


def getTempPath():
    return tempfile.gettempdir() + os.sep


def Version():
    return ["26", "3", "0", "devR20260929 (Git shallow)", "https://github.com/FreeCAD/FreeCAD",
            "3160daf1e2b62b0472854da4848255c6b3ad554c"]


_config = {"SuppressRecomputeRequiredDialog": "", "ExeName": "FreeCAD", "ExeVersion": "26.3.0"}


def ConfigGet(name):
    return _config.get(name, "")


def ConfigSet(name, value):
    _config[name] = value


_observers = []


def addDocumentObserver(obs):
    _observers.append(obs)


def removeDocumentObserver(obs):
    if obs in _observers:
        _observers.remove(obs)


def loadFile(path, *a):
    raise NotImplementedError("loadFile")


class ApplicationDirectories:
    @staticmethod
    def mostRecentConfigFromBase(path):
        return path

    @staticmethod
    def usingCurrentVersionConfig(path):
        return True


class Metadata:
    def __init__(self, path=None):
        self.Name = ""
        self.Content = {}


def isRestoring():
    return False


Units.Units = Units
