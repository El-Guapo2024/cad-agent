# SPDX-License-Identifier: LGPL-2.1-or-later
"""draftutils.params.get_param with a fresh profile's values (as freecadcmd 26.3 reports them)."""
_DEFAULTS = {"precision": 6}


def get_param(entry, path="Mod/Draft", ret_default=False, silent=False):
    return _DEFAULTS[entry]
