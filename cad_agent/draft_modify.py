# SPDX-License-Identifier: LGPL-2.1-or-later
# Draft's modification commands on a part file's objects. The changes are what FreeCAD's own Draft functions make
# (cad_agent/fcdraft/Mod/Draft/draftfunctions/move.py, rotate.py, scale.py, offset.py; FreeCAD 3160daf1e2b6,
# LGPL-2.1-or-later, vendored unchanged), run over the stand-ins on the document as feature_draft.py builds it.
"""cad feature draft SLUG PART OP NAMES...: Draft_Move, Draft_Rotate, Draft_Scale and Draft_Offset on OBJECTS.

    cad feature draft plate Unnamed move Rectangle Circle --vector 10,0,0 [--copy]
    cad feature draft plate Unnamed rotate Rectangle --angle 90 --center 0,0,0 [--axis 0,0,1] [--copy]
    cad feature draft plate Unnamed scale Rectangle --vector 2,2,1 --center 0,0,0 [--copy]
    cad feature draft plate Unnamed offset Wire --vector 0,-1,0 [--copy]      (a circle: --radius 6)

The document's Draft objects are built in one stand-in document (feature_draft._run), a Part object or sketch named
among them as a Part::Feature with its shape and Placement; Draft.move / rotate / scale / offset run on them as the
GUI command's "Draft.move(...)" line does; then each object's properties are read back. An object that changed is a
"set" of what changed (its Placement, or a Rectangle's Length and Height after a scale); a copy is an "add" of the
object Draft made, with its maker's name (Rectangle001). One `cad feature apply` step, named as FreeCAD's commit is.
"""
from __future__ import annotations

from . import feature as F

STEPS = {"move": "Move", "rotate": "Rotate", "scale": "Scale", "offset": "Offset"}


def _vec(App, v, what):
    try:
        x = [float(c) for c in (v.split(",") if isinstance(v, str) else v)]
    except (TypeError, ValueError):
        raise F.FeatureError(f"{what} {v!r} is not x,y,z") from None
    if len(x) != 3:
        raise F.FeatureError(f"{what} {v!r} is not x,y,z")
    return App.Vector(*x)


def _placement(p):
    ypr = p.Rotation.getYawPitchRoll()
    r = lambda x: 0.0 if abs(x) < 1e-12 else round(x, 12)      # noqa: E731
    return ((r(p.Base.x), r(p.Base.y), r(p.Base.z)), tuple(r(a) for a in ypr))


def _props(cls, obj):
    """The keyword values of a stand-in object, as the part file writes them (feature_draft's DEFAULTS)."""
    out = {}
    for k in cls.DEFAULTS:
        if k in cls.REFS or k in ("label", "visibility") or k in cls.ATTACH:
            continue
        if k == "placement":
            out[k] = _placement(obj.Placement)
            continue
        v = getattr(obj, cls.prop_name(k))
        if hasattr(v, "Value"):
            v = v.Value
        if hasattr(v, "x") and hasattr(v, "z"):
            v = (v.x, v.y, v.z)
        elif isinstance(v, list):
            v = tuple((p.x, p.y, p.z) if hasattr(p, "x") else p for p in v)
        out[k] = v
    return out


def _same(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return abs(a - b) <= 1e-9 * max(1.0, abs(a), abs(b))
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    return a == b


def _plain(v):
    if isinstance(v, float):
        return round(v, 9) + 0.0
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    return v


def modify(objects, params, names, op, vector=None, angle=None, center=None, axis=None, radius=None,
           copy=False, features=None, base=None, tip=None) -> list[dict]:
    """The feature ops that Draft's op makes of the named objects."""
    from . import feature_draft as D
    from . import feature_part as P
    if op not in STEPS:
        raise F.FeatureError(f"{op!r} is not one of {', '.join(STEPS)}")
    by = {o.name: o for o in objects}
    for n in names:
        if n not in by:
            raise F.FeatureError(f"no object {n!r}")
    r = P.evaluate(objects, params, features, base, tip)
    ctx = r["_ctx"]
    import FreeCAD as App
    import Draft
    import Part
    st = ctx.__dict__.get("_draft_doc")
    if st is None:                               # no Draft object yet: an empty stand-in document
        st = ctx.__dict__.setdefault("_draft_doc", {"doc": App.newDocument("DraftParts"), "objs": {}})
    doc, objs = st["doc"], st["objs"]
    targets = []
    for n in names:
        if n not in objs:                        # a Part object or a sketch: its shape, at its Placement
            if op not in ("move", "rotate"):
                raise F.FeatureError(f"{n}: Draft's {op} of a {by[n].kind} is not supported here, only of Draft "
                                     "objects")
            f = doc.addObject("Part::Feature", n)
            pl = ctx.placements.get(n)
            f.Shape = Part.Shape(ctx.shapes[n])
            if pl is not None:
                f.Placement = App.Placement(App.Vector(*pl.pos), App.Rotation(*pl.rot.q))
            objs[n] = f
        targets.append(objs[n])
    before = {o.Name for o in doc.Objects}
    snap = {n: _props(type(by[n]), objs[n]) if isinstance(by[n], D.DraftObject) else None for n in names}
    pls = {n: _placement(objs[n].Placement) for n in names}
    if op == "move":
        Draft.move(targets, _vec(App, vector, "--vector"), copy=copy)
    elif op == "rotate":
        if angle is None:
            raise F.FeatureError("rotate needs --angle")
        Draft.rotate(targets, float(angle), _vec(App, center or "0,0,0", "--center"),
                     _vec(App, axis or "0,0,1", "--axis"), copy=copy)
    elif op == "scale":
        Draft.scale(targets, _vec(App, vector, "--vector"), _vec(App, center or "0,0,0", "--center"), copy=copy)
    else:
        if len(targets) != 1:
            raise F.FeatureError("offset takes one object")
        delta = float(radius) if radius is not None else _vec(App, vector, "--vector")
        Draft.offset(targets[0], delta, copy=copy)
    doc.recompute()
    errs = [e for e in getattr(doc, "_errors", []) if e[0] in set(names) | ({o.Name for o in doc.Objects} - before)]
    if errs:
        raise F.FeatureError(f"{errs[0][0]}: {errs[0][1]}")
    ops = []
    for n in names:
        o = by[n]
        if doc.getObject(n) is None:
            continue
        if isinstance(o, D.DraftObject):
            now = _props(type(o), objs[n])
            changed = {k: _plain(v) for k, v in now.items() if not _same(v, snap[n][k])}
        else:
            pl = _placement(objs[n].Placement)
            changed = {"placement": _plain(pl)} if not _same(pl, pls[n]) else {}
        if changed:
            ops.append({"op": "set", "name": n, "props": changed})
    kinds = {c.PROXY[1]: c for c in D.OBJECTS.values()}
    taken = {o.name for o in objects}
    for new in [o for o in doc.Objects if o.Name not in before]:
        ptype = getattr(getattr(new, "Proxy", None), "Type", None)
        cls = kinds.get(ptype)
        if cls is None:     # Draft.scale's non-parametric copy (a polygon, a circle scaled unevenly, a Part object)
            raise F.FeatureError(f"Draft's {op} turns {', '.join(names)} into a plain {new.TypeId} with no Draft "
                                 "properties, which a part file does not hold")
        props = {k: _plain(v) for k, v in _props(cls, new).items()}
        if _same(props.get("placement"), ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0))):
            props.pop("placement")               # the identity: what the part file leaves out
        for k in cls.REFS:
            if k in cls.ATTACH:
                continue
            v = getattr(new, cls.prop_name(k), None)
            if v:
                props[k] = [x.Name for x in v] if isinstance(v, list) else v.Name
        name = new.Name
        while name in taken:
            name += "_"
        taken.add(name)
        ops.append({"op": "add", "feature": {"name": name, "type": cls.TYPE_ID, **props}})
    # an object Draft replaced and removed (scale of a rotated Rectangle: a Wire in its stead)
    ops += [{"op": "delete", "name": n} for n in names if doc.getObject(n) is None]
    return ops


def cmd_feature_draft(a):
    from .featurecmd import UsageError, apply_ops, _cmd, part
    from .feature_attach import _load
    try:
        mod, features, params, base, objects = _load(part(a.slug, a.part))
        ops = modify(objects, params, a.names, a.op, a.vector, a.angle, a.center, a.axis, a.radius, a.copy,
                     features if hasattr(mod, "FEATURES") else None, base, getattr(mod, "TIP", None))
    except F.FeatureError as e:
        raise UsageError(str(e)) from None
    if not ops:
        raise UsageError(f"Draft's {a.op} changed nothing")
    words = [a.op, *a.names] + [f"--{k}={v}" for k in ("vector", "angle", "center", "axis", "radius")
                                if (v := getattr(a, k)) is not None] + (["--copy"] if a.copy else [])
    return apply_ops(a, ops, _cmd(a, *words), STEPS[a.op])


def add_parser(add, fsub):
    sp = add("draft", cmd_feature_draft, "Draft_Move, Draft_Rotate, Draft_Scale or Draft_Offset on objects, as "
             "FreeCAD's Draft functions change them (one undo step)", parent=fsub)
    sp.set_defaults(cmd_name="feature draft", feature_cmd="draft")
    sp.add_argument("slug")
    sp.add_argument("part")
    sp.add_argument("op", choices=tuple(STEPS))
    sp.add_argument("names", nargs="+", metavar="NAME")
    sp.add_argument("--vector", help="move: the displacement; scale: the factors; offset: the delta (x,y,z)")
    sp.add_argument("--angle", type=float, help="rotate: degrees")
    sp.add_argument("--center", help="rotate, scale: the centre (x,y,z; default the origin)")
    sp.add_argument("--axis", help="rotate: the axis (x,y,z; default 0,0,1)")
    sp.add_argument("--radius", type=float, help="offset of a circle: its new radius")
    sp.add_argument("--copy", action="store_true", help="make copies (Draft's copy mode) instead of changing them")
    return sp
