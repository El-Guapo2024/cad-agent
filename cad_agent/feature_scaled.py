# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses FreeCAD's PartDesign::Scaled and keeps FreeCAD's licence, the GNU Lesser
# General Public License, version 2.1 or (at your option) any later version; the text is in ../ui/LICENSE.
#
#   Derived from: src/Mod/PartDesign/App/FeatureScaled.cpp, FeatureScaled.h (Copyright (c) 2012 Jan Rheinländer
#                 <jrheinlaender@users.sourceforge.net>) and src/Mod/PartDesign/App/FeatureMultiTransform.cpp (a
#                 Scaled among a MultiTransform's transformations)
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
"""PartDesign::Scaled for a FEATURES list: the originals and copies of them scaled about the first original's centre
of mass, the last by factor and those between by equal steps.

    Scaled("Scaled", ["Pad001"], factor=2.0, occurrences=3)
    MultiTransform("MultiTransform", ["Pocket"], transformations=[
        LinearPattern("Linear_Pattern", direction="X_Axis", length=20, occurrences=3),
        Scaled("Scale", factor=0.5, occurrences=3)])

Properties (FeatureScaled.cpp): factor (Factor, 2.0), occurrences (Occurrences, 2), and every transformed feature's
originals, transform_mode, refine and suppressed_indices (cad_agent/feature_transform.py). Scaled::getTransformations:
the identity, then occurrences - 1 scalings about the centre of mass of the first original's AddSubShape by
1 + i (factor - 1) / (occurrences - 1); "Scaling factor too small" below Precision::Confusion(), "At least two
occurrences required" under 2. In a MultiTransform each scaling is about the centre of the occurrence it scales, and its
occurrences must divide the ones before it ("Number of occurrences must be a divisor of previous number of
occurrences"): the first slice of them is not scaled, the next by the second factor, and so on.
"""
from __future__ import annotations

from . import feature as F
from .feature_transform import Transformed

try:
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.gp import gp_Pnt, gp_Trsf
except ImportError:                     # pragma: no cover - only FreeCAD's Python lands here
    pass

CONFUSION = 1e-7                        # Precision::Confusion()


def first_original_cog(shapes, originals):
    """The centre of mass of the first original's AddSubShape (the origin when there is none), as Scaled and
    MultiTransform take it."""
    cog = gp_Pnt(0.0, 0.0, 0.0)
    addsub = shapes.get("_addsub", {})
    if originals and originals[0] in addsub and addsub[originals[0]][0] is not None:
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(addsub[originals[0]][0], props)
        cog = props.CentreOfMass()
    return cog


class Scaled(Transformed):
    """PartDesign::Scaled: copies of the originals scaled about the first one's centre of mass."""
    kind = "Scaled"
    TYPE_ID = "PartDesign::Scaled"
    TRANSACTION = "Make Scaled"
    DEFAULTS = {**Transformed.COMMON, "factor": 2.0, "occurrences": 2}
    NONE_SELECTED = "No features selected to be transformed."

    def get_transformations(self, shapes, params, originals):
        factor = float(F.value(self.factor, params, f"{self.name}.factor"))
        if factor < CONFUSION:
            raise ValueError("Scaling factor too small")
        occurrences = int(round(F.value(self.occurrences, params, f"{self.name}.occurrences")))
        if occurrences < 2:
            raise ValueError("At least two occurrences required")
        f = (factor - 1.0) / float(occurrences - 1)
        cog = first_original_cog(shapes, originals)
        out = [gp_Trsf()]                                   # the original, untransformed
        for i in range(1, occurrences):
            t = gp_Trsf()
            t.SetScale(cog, 1.0 + i * f)
            out.append(t)
        return out

    def fill_freecad(self, obj, ctx):
        ctx.setv(obj, "Factor", self.factor)
        ctx.setint(obj, "Occurrences", self.occurrences)
