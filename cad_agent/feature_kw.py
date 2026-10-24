"""A FEATURES entry written as one call with FreeCAD's properties as keywords, that feature_edit reads and edits without
code of its own for the type.

Sketch, Pad and Pocket have their own handling in feature_edit.py (their geometry lists, the deprecated forms FreeCAD
still reads). A feature class derived from KwFeature instead declares what it is:

    kind       the call's name in the part file, and FreeCAD's short type name ("Mirrored", "AdditiveBox")
    TYPE_ID    FreeCAD's TypeId ("PartDesign::Mirrored")
    POS        the arguments after the name that the call takes by position, in order (("originals",))
    DEFAULTS   every property, snake_case as FreeCAD's name (MirrorPlane -> mirror_plane), with FreeCAD's default
    REFS       the properties that name other features: a name, (name, sub-element) or a list of those
    NESTED     the properties that hold feature objects of their own (MultiTransform's transformations)
    TRANSACTION the undo step FreeCAD opens when it makes one ("Make Mirrored")

and feature_edit reads it (props() gives the JSON-ready dict), writes it (only what is not a default), sets, renames the
references to a feature and refuses to delete a feature something still references, all from these declarations.

A reference is FreeCAD's PropertyLinkSub, (object, sub-element): an origin feature by its name ("XY_Plane", "X_Axis"),
("Sketch", "V_Axis") for a sketch's axis, ("Pad", "Face6") or ("Pad", "Edge3") for an element of a feature's shape.
This module imports without build123d or OCP, as feature.py does.
"""
from __future__ import annotations

from . import feature as F

# The Body's Origin, by the names FreeCAD gives its features (App::Origin's X_Axis ... YZ_Plane, Origin as the point).
ORIGIN = ("X_Axis", "Y_Axis", "Z_Axis", "XY_Plane", "XZ_Plane", "YZ_Plane")


def ref(v, where: str):
    """A reference as the part file holds it: "XY_Plane", or (name, sub). JSON's lists become tuples."""
    if v is None or isinstance(v, str):
        return v
    if isinstance(v, (list, tuple)) and len(v) == 2 and isinstance(v[0], str):
        sub = v[1]
        if isinstance(sub, (list, tuple)):       # FreeCAD's (obj, ['V_Axis'])
            sub = sub[0] if sub else ""
        if not isinstance(sub, str):
            raise F.FeatureError(f"{where}: {v!r} is not (feature, sub-element)")
        return (v[0], sub)
    raise F.FeatureError(f"{where}: {v!r} is not a reference: a feature's name, or (feature, sub-element) such as "
                         "(\"Sketch\", \"V_Axis\") or (\"Pad\", \"Face6\")")


def ref_name(r) -> str | None:
    return r if isinstance(r, str) else r[0] if r else None


def _json(v):
    if isinstance(v, tuple):
        return [_json(x) for x in v]
    if isinstance(v, list):
        return [_json(x) for x in v]
    if isinstance(v, KwFeature):
        return v.as_dict()
    return v


class KwFeature:
    kind = ""
    TYPE_ID = ""
    POS: tuple = ()
    DEFAULTS: dict = {}
    REFS: tuple = ()
    NESTED: tuple = ()
    TRANSACTION = ""

    def __init__(self, name: str, *args, **kw):
        if not isinstance(name, str) or not name:
            raise F.FeatureError(f"a {self.kind} needs a name")
        self.name = name
        if len(args) > len(self.POS):
            raise F.FeatureError(f"{name}: {self.kind}() takes {len(self.POS) + 1} positional arguments")
        for k, v in zip(self.POS, args):
            if k in kw:
                raise F.FeatureError(f"{name}: {k} given twice")
            kw[k] = v
        unknown = set(kw) - set(self.DEFAULTS)
        if unknown:
            raise F.FeatureError(f"{name}: {', '.join(sorted(unknown))} is not a property of a {self.kind}")
        for k, d in self.DEFAULTS.items():
            setattr(self, k, self.normalize(k, kw[k] if k in kw else d))
        self.validate()

    # ── what a subclass may refine ──
    def normalize(self, key, v):
        """A property's value as this module keeps it (JSON's lists to tuples for references, ...)."""
        if key in self.REFS:
            if self.is_ref_list(key):
                if isinstance(v, str):
                    v = [v]
                return tuple(ref(x, f"{self.name}.{key}") for x in (v or ()))
            return ref(v, f"{self.name}.{key}")
        if key in self.NESTED:
            return list(v or [])
        d = self.DEFAULTS[key]
        if isinstance(d, tuple) and isinstance(v, list):
            return tuple(tuple(x) if isinstance(x, list) else x for x in v)
        if isinstance(d, bool):
            return bool(v)
        return v

    def validate(self):
        pass

    # ── what feature_edit uses ──
    def as_dict(self) -> dict:
        return {"name": self.name, "type": self.TYPE_ID, **{k: _json(getattr(self, k)) for k in self.DEFAULTS}}

    @classmethod
    def from_dict(cls, d: dict) -> "KwFeature":
        kw = {}
        for k, v in d.items():
            if k in ("name", "type"):
                continue
            if k in cls.NESTED:
                v = [nested_from_dict(x) for x in (v or [])]
            kw[k] = v
        return cls(d.get("name"), **kw)

    def source_value(self, key, v=None):
        """A property's value as the part file writes it (feature_edit's lit): one reference as a name or a
        (name, sub) tuple, a placement as tuples, every other list as a list."""
        v = getattr(self, key) if v is None else v
        if key in self.REFS and not self.is_ref_list(key):
            return v
        if key in self.REFS:
            return list(v)
        if key == "placement":
            return v
        if isinstance(v, tuple):
            return list(v)
        return v

    @classmethod
    def is_ref_list(cls, key) -> bool:
        """Whether a reference property holds a list (PropertyLinkList, Originals) rather than one link."""
        return key in cls.REFS and isinstance(cls.DEFAULTS[key], (list, tuple))

    def is_default(self, key) -> bool:
        return self.normalize(key, self.DEFAULTS[key]) == getattr(self, key)

    def references(self) -> list[str]:
        """The names of the features this one references, nested ones included."""
        out = []
        for k in self.REFS:
            v = getattr(self, k)
            for r in (v if self.is_ref_list(k) else [v]):
                n = ref_name(r)
                if n:
                    out.append(n)
        for k in self.NESTED:
            for f in getattr(self, k):
                out += f.references()
        return out

    def nested_names(self) -> list[str]:
        out = []
        for k in self.NESTED:
            for f in getattr(self, k):
                out += [f.name] + f.nested_names()
        return out

    def __repr__(self):
        return f"{self.kind}({self.name!r})"


def nested_from_dict(x):
    if isinstance(x, KwFeature):
        return x
    if not isinstance(x, dict):
        raise F.FeatureError(f"{x!r} is not a feature")
    kind = x.get("type", "")
    kind = kind.split("::")[-1]
    cls = F.FEATURES.get(kind)
    if cls is None or not issubclass(cls, KwFeature):
        raise F.FeatureError(f"{x.get('type')!r} is not a feature that can go there")
    return cls.from_dict(x)


def classes() -> dict:
    """{kind: class} of every KwFeature in feature.FEATURES."""
    return {k: c for k, c in F.FEATURES.items() if isinstance(c, type) and issubclass(c, KwFeature)}


def kw_class(kind):
    """The KwFeature class a part file's call name (or FreeCAD's short type name) is, or None."""
    c = F.FEATURES.get(kind) if isinstance(kind, str) else None
    return c if isinstance(c, type) and issubclass(c, KwFeature) else None


def type_ids() -> dict:
    """{kind: TypeId} for feature_edit.TYPE_IDS."""
    return {k: c.TYPE_ID for k, c in classes().items()}


def bare(cls, name: str = "x"):
    """An instance with no properties set, for its normalize() and source_value() alone."""
    obj = object.__new__(cls)
    obj.name = name
    return obj
