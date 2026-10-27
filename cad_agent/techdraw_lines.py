# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses FreeCAD's TechDraw line styles and keeps FreeCAD's licence, the GNU Lesser
# General Public License, version 2.1 or (at your option) any later version; the text is in ../ui/LICENSE.
#
#   Derived from: src/Mod/TechDraw/App/LineGenerator.cpp (Copyright (c) 2022 WandererFan),
#                 src/Mod/TechDraw/LineGroup/ASME.Y14.2.2008.LineDef.csv and .ElementDef.csv (FreeCAD, LGPL-2.1-or-later)
#                 FreeCAD (https://github.com/FreeCAD/FreeCAD), commit 3160daf1e2b62b0472854da4848255c6b3ad554c
#
#   This library is free software; you can redistribute it and/or modify it under the terms of the GNU Library
#   General Public License as published by the Free Software Foundation; either version 2 of the License, or
#   (at your option) any later version.
#
#   This library is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the
#   implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU Library General Public
#   License for more details.
#
# See ../NOTICE.
"""The line styles of a fresh profile's TechDraw (Preferences > TechDraw > Standards > Line Standard 1: ASME Y14.2-2008):
the 17 named lines the style combo boxes list (loadLineStyleChoices), and the dash pattern each draws
(LineGenerator::getLinePen). A format's `line_number` picks one (1-based); where it is out of range, its Qt `style`
does (fromQtStyle); a style of none of those is continuous.

ASME's elements are not proportional to the pen: a pattern's lengths are millimetres, whatever the weight.
"""
from __future__ import annotations

# ASME.Y14.2.2008.ElementDef.csv: element, length
ELEMENTS = {"Dot": 1, "Gap": 3, "ShortDash": 6, "Dash": 12, "LongDash": 24, "Space": 12}
# ASME.Y14.2.2008.LineDef.csv: number, name, elements ("n/a": continuous, "noline": not drawn)
LINES = [
    ("Visible", None), ("Hidden", ("Dash", "Gap")), ("Section", None), ("Center", ("LongDash", "Space", "Dash", "Space")),
    ("Symmetry", ("LongDash", "Space", "Dash", "Space")), ("Dimension", None), ("Extension", None), ("Leader", None),
    ("Cutting-plane", ("Dash", "Gap")), ("Viewing-plane", ("Space", "Dash", "Space", "Dash", "Space", "LongDash", "Space")),
    ("Other plane", "noline"), ("Break 1", None), ("Break 2", None),
    ("Phantom", ("LongDash", "Space", "Dash", "Space", "Dash", "Space")), ("Stitch 1", ("Dash", "Space")),
    ("Stitch 2", ("Dot", "Gap")), ("Chain", ("LongDash", "Space", "Dash", "Space")),
]
NAMES = [n for n, _ in LINES]
# Qt::PenStyle as the formats store it: NoPen 0, SolidLine 1, DashLine 2, DotLine 3, DashDotLine 4, DashDotDotLine 5, Custom 6
QT_TO_LINE = {0: 1, 1: 1, 2: 2, 3: 16, 4: 17, 5: 14, 6: 2}      # LineGenerator::fromQtStyle under ASME


def from_qt_style(style: int) -> int:
    return QT_TO_LINE.get(int(style), 0)


def pen(line_number: int, style: int = 1):
    """(dash pattern in mm or None for a continuous line, whether the line is drawn at all), LineGenerator::getBestPen:
    the line number when it is valid, else the Qt style's, else continuous."""
    n = line_number if 0 < line_number < len(LINES) + 1 else (from_qt_style(style) or 1)
    name, elements = LINES[n - 1]
    if elements is None:
        return None, True
    if elements == "noline":
        return None, False
    seq = list(elements)
    if seq[0] in ("Gap", "Space"):
        seq = seq[1:]       # (Qt's pattern starts with a mark: the offset is dropped here)
    pattern = [float(ELEMENTS[e]) for e in seq]
    if len(pattern) % 2:
        pattern.append(pattern[0])        # (Qt repeats an odd pattern: mark, space, mark ... space, mark)
    return pattern, True
