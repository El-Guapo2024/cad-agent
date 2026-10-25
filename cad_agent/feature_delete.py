# SPDX-License-Identifier: LGPL-2.1-or-later
# Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
# LGPL-2.0-or-later or LGPL-2.1-or-later as it states; NOTICE has them all):
#   src/Gui/CommandDoc.cpp: 2002 Jürgen Riegel (StdCmdDelete: "Object Dependencies", then the delete)
#   src/App/PropertyLinks.cpp: 2002 Jürgen Riegel (breakLink: a link to the deleted object is cleared, a list's entry dropped)
#   src/Mod/PartDesign/App/Body.cpp: 2015 Stefan Tröger (removeObject: the next solid's BaseFeature is the one before)
#   src/Mod/PartDesign/App/FeatureDressUp.cpp: 2010 Juergen Riegel (onBaseFeatureRerouted: the Base follows to it)
"""Std_Delete answered Yes: the feature goes, and what linked it breaks as FreeCAD breaks it.

FreeCAD asks first ("The following referencing objects might break. Continue?", the page's partdesign.tsx) and then
deletes; each link to the deleted object is broken (PropertyLink::breakLink): a single link is cleared, a list's entry
dropped. What the real FreeCAD 26.3 does with the dependents (ui/scripts/fcpick.json, "delete"):

  an attachment       its support loses the object; with none left the object keeps the Placement it had (a sketch
                      attached to a deleted datum plane stays where it was). Here that is map_mode "Deactivated" with
                      that placement: the part file has no "FlatFace with no support" (it would read as on XY).
  a dress-up's Base   rerouted to the solid before the deleted one (Body::removeObject, onBaseFeatureRerouted): a
                      Fillet on Pad001's Edge1 is a Fillet on Pad's Edge1, its element then followed by feature_edit's
                      follow_src as an edit follows it.
  a list link         the entry is dropped (a pattern's Originals).
  a single link       cleared (an Up to face, a mirror plane, a pattern's direction, a Draft's neutral plane).

A link the feature cannot do without (a Pad's Profile: FreeCAD leaves the Pad in error, "No object linked"; a sketch's
external geometry) is left as it is, so the delete is refused with the name of what still uses it: a part file only
holds a Body that builds.
"""
from __future__ import annotations

from pathlib import Path

from . import feature as F
from . import feature_kw as KW

SOLID_SKIP = ("Sketcher::SketchObject",)


def _is_solid(d: dict) -> bool:
    from .feature_attach import DATUMS
    return d.get("type") not in SOLID_SKIP and d.get("type") not in {c.TYPE_ID for c in DATUMS.values()}


def _frozen(src: str, name: str):
    """The placement the Body gives `name` now, as ((x, y, z), (yaw, pitch, roll)), or None when it cannot be built."""
    from . import feature_edit as E
    try:
        feats, params, base = E._run(src, Path("_part.py"))
        ctx = F.evaluate(feats, params, base)["_attach"]
    except Exception:              # a part that does not build here: its own build says why
        return None
    pl = ctx.placements.get(name)
    if pl is None:
        return None
    yaw, pitch, roll = pl.rot.ypr()
    r = lambda x: round(x, 12) + 0.0     # noqa: E731
    return ((r(pl.pos[0]), r(pl.pos[1]), r(pl.pos[2])), (r(yaw), r(pitch), r(roll)))


def break_links(src: str, name: str) -> str:
    """src with every link to the feature `name` broken as FreeCAD breaks it, before the delete."""
    from . import feature_edit as E
    doc = E.read_src(src)
    feats = doc["features"]
    names = [f["name"] for f in feats]
    if name not in names:
        return src
    i = names.index(name)
    before = next((f["name"] for f in reversed(feats[:i]) if _is_solid(f)), "BaseFeature" if doc.get("base") else None)
    ops = []
    for f in feats:
        if f["name"] == name:
            continue
        props: dict = {}
        sup = f.get("attachment_support") or []
        if any(r[0] == name for r in sup):
            left = [r for r in sup if r[0] != name]
            props["attachment_support"] = left
            if not left:
                frozen = _frozen(src, f["name"])
                if frozen is not None:
                    props["map_mode"] = "Deactivated"
                    props["placement"] = frozen
        cls = KW.kw_class(E.KINDS.get(f.get("type"), ""))
        if cls is not None:
            from .feature_dressup import DRESSUPS
            for key in cls.REFS:
                if key == "attachment_support":
                    continue
                dk = cls.DICT_KEYS.get(key, key)
                v = f.get(dk)
                if v is None:
                    continue
                if key == "base" and cls in DRESSUPS.values():
                    if isinstance(v, list) and v and v[0] == name and before:
                        props[dk] = [before, v[1] if len(v) > 1 else []]     # onBaseFeatureRerouted
                    continue
                if cls.is_ref_list(key):
                    kept = [r for r in v if KW.ref_name(r if isinstance(r, str) else tuple(r)) != name]
                    if len(kept) != len(v):
                        props[dk] = kept
                elif KW.ref_name(v if isinstance(v, str) else tuple(v)) == name:
                    props[dk] = None
        elif f.get("type") in (E.TYPE_IDS["Pad"], E.TYPE_IDS["Pocket"]):
            for key in ("up_to_face", "up_to_face2", "reference_axis"):
                v = f.get(key)
                if v is not None and (v == name or (isinstance(v, list) and v and v[0] == name)):
                    props[key] = None
            for key in ("up_to_shape", "up_to_shape2"):
                v = f.get(key)
                if isinstance(v, list) and v:
                    kept = [r for r in v if (r if isinstance(r, str) else r[0]) != name]
                    if len(kept) != len(v):
                        props[key] = kept or None
        if props:
            ops.append({"op": "set", "name": f["name"], "props": props})
    return E.apply_src(src, ops) if ops else src
