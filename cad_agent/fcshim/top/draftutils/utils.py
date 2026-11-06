# SPDX-License-Identifier: LGPL-2.1-or-later
"""draftutils.utils.precision (src/Mod/Draft/draftutils/utils.py): the Draft precision parameter."""
from draftutils import params


def precision():
    return params.get_param("precision")
