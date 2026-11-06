# SPDX-License-Identifier: LGPL-2.1-or-later
from ._dummy import QObject, Signal, _Inert, module_getattr  # noqa: F401


def Slot(*a, **k):  # noqa: N802
    return lambda f: f


def Property(*a, **k):  # noqa: N802
    return lambda f: f


def QT_TRANSLATE_NOOP(context, text):  # noqa: N802
    return text


class QCoreApplication:
    @staticmethod
    def instance():
        return None

    @staticmethod
    def translate(context, text, *a):
        return text

    @staticmethod
    def processEvents(*a):
        pass


Qt = _Inert()


# Qt resource paths (":/ui/x.ui") the runtimes resolve to folders of the vendored files (draft_runtime: Draft's .ui)
RESOURCE_DIRS: dict = {}


class QIODevice:
    ReadOnly = 1
    Text = 16


class _Bytes:
    def __init__(self, b):
        self._b = b

    def data(self):
        return self._b


class QFile:
    """QFile over the vendored resources (RESOURCE_DIRS) and plain files: open, readAll, close."""
    Text = QIODevice.Text

    def __init__(self, name):
        self._name, self._data = str(name), None

    def _path(self):
        from pathlib import Path
        if self._name.startswith(":/"):
            for prefix, d in RESOURCE_DIRS.items():
                if self._name.startswith(prefix):
                    return Path(d) / self._name[len(prefix):]
            return None
        return Path(self._name)

    def open(self, mode=None):
        p = self._path()
        if p is None or not p.is_file():
            return False
        self._data = p.read_bytes()
        return True

    def readAll(self):
        return _Bytes(self._data or b"")

    def close(self):
        self._data = None

    def exists(self):
        p = self._path()
        return p is not None and p.is_file()


class QStandardPaths:
    """Draft's params look for a default ShapeString font in the system's font folders: none here."""
    FontsLocation = 1

    @staticmethod
    def standardLocations(kind):
        return []


class QTimer(QObject):
    @staticmethod
    def singleShot(ms, fn):
        pass


def __getattr__(name):
    return module_getattr(name)
