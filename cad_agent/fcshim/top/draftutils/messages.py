# SPDX-License-Identifier: LGPL-2.1-or-later
"""draftutils.messages: Draft's console helpers, onto the stand-in FreeCAD's Console."""
import FreeCAD as App


def _msg(text, end="\n"):
    App.Console.PrintMessage(text + end)


def _wrn(text, end="\n"):
    App.Console.PrintWarning(text + end)


def _err(text, end="\n"):
    App.Console.PrintError(text + end)


def _log(text, end="\n"):
    App.Console.PrintLog(text + end)
