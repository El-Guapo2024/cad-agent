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


class QTimer(QObject):
    @staticmethod
    def singleShot(ms, fn):
        pass


def __getattr__(name):
    return module_getattr(name)
