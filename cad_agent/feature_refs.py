# SPDX-License-Identifier: LGPL-2.1-or-later
# Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
# LGPL-2.0-or-later or LGPL-2.1-or-later as it states; NOTICE has them all):
#   src/App/Datums.cpp: 2015 Alexander Golubev (Fat-Zer) (DatumElement::getBasePoint, getDirection, the base directions)
#   src/Mod/Part/App/Datums.cpp: 2024 Ondsel (Part::DatumLine's base direction Z)
#   src/Mod/PartDesign/App/DatumPlane.cpp, DatumLine.cpp: 2013 Jan Rheinländer (getNormal, getDirection, getBasePoint)
#   src/Mod/PartDesign/App/FeatureSketchBased.cpp: 2010 Juergen Riegel (getUpToFaceFromLinkSub, getAxis)
"""The Body's datums as references: what a Pad's Up to face, a Revolution's or a Pad's axis, a Mirrored's plane, a
pattern's direction or axis and a Draft's neutral plane or pull direction get from a datum, as FreeCAD's features read
them.

FreeCAD's datums are of two families, and the features treat them apart:
  App datum elements   the Body's Origin features, Part::DatumPlane and Part::DatumLine (Part_DatumPlane ...: App::Plane
                       and App::Line with AttachExtension) and an LCS's features. getBasePoint() is the Placement's
                       position (an LCS's feature adds the LCS's position), getDirection() the Placement's rotation of
                       the base direction (Z for a plane and for Part::DatumLine, X for App::Line), then the LCS's.
  PartDesign datums    PartDesign::Plane and PartDesign::Line (Part::Datum, a Part::Feature): getNormal() and
                       getDirection() are the rotation of Z, getBasePoint() the position. A feature that does not ask
                       for them by type reads them as a Part::Feature, whose reference needs a sub-element; a datum
                       picked in the GUI has none (getReferencedSelection empties it), so FreeCAD refuses it there.

A reference to one is its name, "DatumPlane", or for an LCS's feature ("LCS", "XY_Plane") (what TaskSketchBasedParameters
writes: the LCS and its feature's name). The Body's attachment context (shapes["_attach"], feature_attach.Context) knows
where each is.
"""
from __future__ import annotations

from . import feature as F

# DatumElement's base direction (App/Datums.cpp): a plane's normal and App::Line's direction; Part::DatumLine's is Z
_BASE = {"App::Plane": (0.0, 0.0, 1.0), "App::Line": (1.0, 0.0, 0.0), "App::Point": (0.0, 0.0, 0.0)}
# The type each datum of feature_attach is, as the features test it (isDerivedFrom)
_TYPE = {"DatumPlane": "App::Plane", "DatumLine": "App::Line", "DatumPoint": "App::Point",
         "LocalCoordinateSystem": "App::LocalCoordinateSystem", "PartDesignPlane": "PartDesign::Plane",
         "PartDesignLine": "PartDesign::Line", "PartDesignPoint": "PartDesign::Point",
         "PartDesignCoordinateSystem": "PartDesign::CoordinateSystem"}


def _ctx(shapes):
    return shapes.get("_attach") if isinstance(shapes, dict) else None


def _split(r):
    if r is None:
        return None, ""
    if isinstance(r, str):
        return r, ""
    name, sub = r
    if isinstance(sub, (list, tuple)):
        sub = sub[0] if sub else ""
    return name, sub or ""


def _role(sub):
    from .feature_attach import ORIGIN
    return next((r for r in ORIGIN if sub.startswith(r)), None)


def datum_type(shapes, r) -> str | None:
    """The type of the datum a reference names, as FreeCAD's isDerivedFrom tests see it: "App::Plane", "App::Line",
    "App::Point" (an Origin feature, a Part datum, an LCS's feature), "PartDesign::Plane", "PartDesign::Line",
    "PartDesign::Point", "PartDesign::CoordinateSystem", "App::LocalCoordinateSystem" (the LCS itself); None for
    anything else (a solid, a sketch, a face of one)."""
    from .feature_attach import ORIGIN
    name, sub = _split(r)
    if name is None:
        return None
    if name in ORIGIN:
        return ORIGIN[name][0]
    ctx = _ctx(shapes)
    d = ctx.datums.get(name) if ctx is not None else None
    if d is None:
        return None
    t = _TYPE.get(d.kind)
    if t == "App::LocalCoordinateSystem" and sub:
        role = _role(sub)
        return ORIGIN[role][0] if role else None
    return t


def is_datum(shapes, r) -> bool:
    return datum_type(shapes, r) is not None


def _placement(shapes, r):
    """(placement, base direction) of an App datum element: its own, or for an LCS's feature the LCS's times the role's."""
    from . import attacher as A
    from .feature_attach import ORIGIN
    name, sub = _split(r)
    ctx = _ctx(shapes)
    t = datum_type(shapes, r)
    if name in ORIGIN:
        pl = ctx.placements[name] if ctx is not None else A.Placement((0, 0, 0), A.Rotation(ORIGIN[name][1], normalize=False))
        return pl, _BASE[ORIGIN[name][0]]
    pl = ctx.placements[name]
    d = ctx.datums[name]
    if d.kind == "LocalCoordinateSystem":
        role = _role(sub)
        kind, q = ORIGIN[role]
        # getBasePoint adds the LCS's position to the feature's own (zero); getDirection turns by both rotations
        return A.Placement(pl.pos, pl.rot * A.Rotation(q, normalize=False)), _BASE[kind]
    if t == "App::Line":
        return pl, (0.0, 0.0, 1.0)              # Part::DatumLine: setBaseDirection(0, 0, 1)
    return pl, _BASE.get(t, (0.0, 0.0, 1.0))


def base_and_direction(shapes, r):
    """DatumElement::getBasePoint and getDirection of an App datum element, or PartDesign::Plane's getBasePoint and
    getNormal, PartDesign::Line's getBasePoint and getDirection: (point, direction) as tuples, in the Body's frame."""
    t = datum_type(shapes, r)
    if t is None:
        raise F.FeatureError(f"{r!r} is not a datum")
    if t.startswith("PartDesign::"):
        name, _ = _split(r)
        pl = _ctx(shapes).placements[name]
        return tuple(pl.pos), tuple(pl.rot.mult_vec((0.0, 0.0, 1.0)))
    pl, base = _placement(shapes, r)
    return tuple(pl.pos), tuple(pl.rot.mult_vec(base))


def plane_face(shapes, r):
    """ProfileBased::getUpToFaceFromLinkSub for a datum: an App::Plane is makeShapeFromPlane (the infinite face on its
    Placement); a PartDesign::Plane and an LCS's plane are their shape (getTopoShape), the same face. None when the
    reference is not a datum plane."""
    t = datum_type(shapes, r)
    if t not in ("App::Plane", "PartDesign::Plane"):
        return None
    name, sub = _split(r)
    shape = _ctx(shapes).element(name, sub, f"up to face {name}")
    from OCP.TopAbs import TopAbs_FACE
    faces = F._subs(shape, TopAbs_FACE) if shape is not None else []
    if not faces:
        raise F.FeatureError("SketchBased: Up to face: Failed to extract face")
    return faces[0]


def freecad_ref(r, ctx, lcs_sub: bool = False):
    """A reference as FreeCAD's PropertyLinkSub takes it, in feature.to_freecad's ctx: an Origin feature or a datum by
    its object with no sub-element ([""], as getReferencedSelection leaves a datum), an LCS's feature by the App::Plane or
    App::Line object the LCS holds for the role (what a click on it selects), else (object, [sub]). lcs_sub: an LCS's
    feature as (LCS, [its name]), what TaskSketchBasedParameters::onAddSelection writes for an Up to face."""
    from .feature_attach import ORIGIN
    name, sub = _split(r)
    if name in ORIGIN:
        return ctx.origin[name], [""]
    obj = ctx.made[name]
    if sub and obj.TypeId == "Part::LocalCoordinateSystem":
        role = _role(sub)
        feat = next((o for o in obj.OriginFeatures if o.Role == role), None)
        if feat is not None:
            return (obj, [feat.Name]) if lcs_sub else (feat, [""])
    if obj.TypeId.startswith(("Part::Datum", "PartDesign::Plane", "PartDesign::Line", "PartDesign::Point")):
        return obj, [""]
    return obj, [sub]


def own_plane(shapes, r):
    """Feature::makePlnFromPlane of an App::Plane (a Draft's neutral plane): (point, normal) of its own Placement and Z.
    For an LCS's plane that is the role's Placement alone, the LCS's own left out, as FreeCAD's reads it."""
    from . import attacher as A
    from .feature_attach import ORIGIN
    name, sub = _split(r)
    ctx = _ctx(shapes)
    if name in ORIGIN or ctx.datums[name].kind != "LocalCoordinateSystem":
        pl = ctx.placements[name]
    else:
        pl = A.Placement((0, 0, 0), A.Rotation(ORIGIN[_role(sub)][1], normalize=False))
    return tuple(pl.pos), tuple(pl.rot.mult_vec((0.0, 0.0, 1.0)))
