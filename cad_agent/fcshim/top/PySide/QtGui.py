# SPDX-License-Identifier: LGPL-2.1-or-later
from ._dummy import module_getattr


def __getattr__(name):
    return module_getattr(name)
