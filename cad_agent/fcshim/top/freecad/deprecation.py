# SPDX-License-Identifier: LGPL-2.1-or-later
"""freecad.deprecation (src/Ext/freecad/deprecation.py): the decorator, without its warnings."""


def deprecated(*dargs, **dkw):
    if len(dargs) == 1 and callable(dargs[0]) and not dkw:
        return dargs[0]

    def wrap(f):
        return f
    return wrap


def _unwrap_deprecated_frame(frame):
    return frame
