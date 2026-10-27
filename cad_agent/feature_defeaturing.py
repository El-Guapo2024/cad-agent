# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It ports FreeCAD's PartDesign::Defeaturing and keeps FreeCAD's licence, the GNU Lesser General
# Public License, version 2.1 or (at your option) any later version; the text is in ../ui/LICENSE.
#
#   Derived from FreeCAD (https://github.com/FreeCAD/FreeCAD), commit 3160daf1e2b62b0472854da4848255c6b3ad554c:
#     src/Mod/PartDesign/App/FeatureDefeaturing.cpp: Copyright (c) 2026 Max Wilfinger (execute)
#     src/Mod/Part/App/TopoShapeExpansion.cpp: Copyright (c) 2022 Zheng, Lei (makeElementDefeaturing)
#     src/Mod/PartDesign/App/FeatureDressUp.cpp: Copyright (c) 2010 Juergen Riegel (getFaces)
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
"""PartDesign::Defeaturing in a FEATURES list: the solid before it with some of its faces removed, the gap closed by
extending the faces around them (OCCT's BRepAlgoAPI_Defeaturing), as a dress-up takes its faces:

    Defeaturing("Defeaturing", ("Pocket", ["Face7", "Face8"]))

Its properties are a dress-up's, Base (the solid before it and the FaceN to remove) and Refine (FreeCAD's default,
True); FeatureDefeaturing.cpp adds none. With no face it is a copy of its base (not refined, as execute() returns
early); a face that does not belong to the base is "Invalid Invalid face link" (DressUp::getFaces); a removal OCCT
cannot make is its error report (BRepAlgoAPI_Defeaturing::DumpErrors), or "Defeaturing failed: result is null".
OCP is imported when the feature builds, not when the part file is read.
"""
from __future__ import annotations

from . import feature as F
from .feature_dressup import _DressUp, _faces_of_base


class Defeaturing(_DressUp):
    """PartDesign::Defeaturing (FeatureDefeaturing.cpp): a dress-up that removes the Base's faces."""
    kind = "Defeaturing"
    TYPE_ID = "PartDesign::Defeaturing"
    TRANSACTION = "Make Defeaturing"      # finishDressupFeature: openCommand("Make " + which)
    DEFAULTS = {"base": None, "refine": True}

    def _make(self, base, shapes, params):
        """Defeaturing::execute: getFaces of the base; none, a copy of it; else makeElementDefeaturing, refined."""
        faces = _faces_of_base(self, base)
        if not faces:
            return base
        res = defeature(base, faces)
        return self._refined(res)


def defeature(shape, faces):
    """TopoShape::makeElementDefeaturing: BRepAlgoAPI_Defeaturing of the shape with the faces to remove (run in
    parallel, with its history, as FreeCAD runs it)."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Defeaturing
    from OCP.TopAbs import TopAbs_FACE
    if shape is None or shape.IsNull():
        raise F.FeatureError("Null shape")
    if not faces:
        raise F.FeatureError("Null input shape")
    mk = BRepAlgoAPI_Defeaturing()
    mk.SetRunParallel(True)
    mk.SetToFillHistory(True)
    mk.SetShape(shape)
    for face in faces:
        if face is None or face.IsNull():
            raise F.FeatureError("Null input shape")
        if face.ShapeType() != TopAbs_FACE:
            raise F.FeatureError("defeaturing input shape is not a face")
        mk.AddFaceToRemove(face)
    mk.Build()
    if not mk.IsDone():
        raise F.FeatureError(_errors(mk) or "Defeaturing failed")
    out = mk.Shape()
    if out is None or out.IsNull():
        raise F.FeatureError("Defeaturing failed: result is null")
    return out


def _errors(mk) -> str:
    """BRepAlgoAPI_Defeaturing::DumpErrors, as FreeCAD's Base::RuntimeError carries it."""
    try:
        import io
        buf = io.StringIO()
        mk.DumpErrors(buf)
        return buf.getvalue().strip()
    except Exception:  # noqa: BLE001 - a binding without the stream: the bare message
        return ""
