# SPDX-License-Identifier: LGPL-2.1-or-later
"""What FreeCAD's CAM Python touches of Qt with no GUI: classes it subclasses or names at import time, signals it
connects, QT_TRANSLATE_NOOP. Nothing is drawn; every other name is an inert stand-in."""


class _InertMeta(type):
    def __getattr__(cls, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _Inert()


class _Inert(metaclass=_InertMeta):
    def __init__(self, *a, **k):
        pass

    def __call__(self, *a, **k):
        return _Inert()

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _Inert()

    def __bool__(self):
        return False

    def __iter__(self):
        return iter(())

    def __int__(self):
        return 0

    def __or__(self, o):
        return self

    __ror__ = __or__


class Signal:
    def __init__(self, *types, **k):
        self._name = None

    def __set_name__(self, owner, name):
        self._name = name

    def __get__(self, obj, owner=None):
        if obj is None:
            return self
        key = "_signal_" + (self._name or str(id(self)))
        inst = obj.__dict__.get(key)
        if inst is None:
            inst = _BoundSignal()
            obj.__dict__[key] = inst
        return inst


class _BoundSignal:
    def __init__(self):
        self._slots = []

    def connect(self, slot, *a):
        self._slots.append(slot)

    def disconnect(self, slot=None):
        if slot is None:
            self._slots.clear()
        elif slot in self._slots:
            self._slots.remove(slot)

    def emit(self, *args):
        for s in list(self._slots):
            s(*args)


class QObject:
    def __init__(self, *a, **k):
        pass

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return _Inert()


def module_getattr(name):
    if name.startswith("__"):
        raise AttributeError(name)
    return type(name, (_Inert,), {})
