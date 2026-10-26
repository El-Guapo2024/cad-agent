# SPDX-License-Identifier: LGPL-2.1-or-later
"""feature_edit for the Part workbench's objects: OBJECTS, the document's list beside a Body's FEATURES.

cad_agent/feature_part.py has the part file's form. feature_edit.py reads and edits OBJECTS entries with the same code
as FEATURES entries (they are feature_kw.KwFeature calls, Part.Box(...), or Sketch(...) calls); this module holds what
is OBJECTS' own:

    an "add" goes to OBJECTS when its type is a Part object ("Part::Box") or when the op says "list": "OBJECTS" (a
    Sketch made outside a Body, Sketcher_NewSketch with no active Body). The first one turns the part file into a
    document: a Body file's build() `return Body(FEATURES, p, ...)` becomes `return Part.Document(OBJECTS, p, FEATURES,
    ...)` with `OBJECTS = []` after the feature list; a hand-written part first gets its Body (feature_edit._convert),
    its solid the Body's BaseFeature. A document made new is DOCUMENT_TEMPLATE (`cad feature new --document`).
    A PartDesign feature added to a document that has no Body yet gives it one: FEATURES = [] and TIP, which
    Part.Document takes.

    read() gains "objects" (each one's dict, as features' are) and "body" (whether the part has FEATURES) when the file
    has OBJECTS. Names are unique over both lists and "Body" (FreeCAD's document has one namespace); an object links
    only what is before it in OBJECTS, the Body, or the Body's features.
"""
from __future__ import annotations

import ast

from . import feature as F
from . import feature_edit as E
from . import feature_kw as KW

IMPORT = "from cad_agent import feature_part as Part\n"
DOCUMENT_TEMPLATE = '''"""{part}: Part workbench objects made in the workbench (cad feature new --document).

Its shape is OBJECTS, the document's Part objects in FreeCAD's order (cad_agent/feature_part.py): every object no other
object uses is shown. The workbench edits the list in place; so can you.
"""
from cad_agent import feature_part as Part
from cad_agent.feature import (ArcOfCircle, Circle, Constraint, LineSegment, Point, Sketch)

MATERIAL = {material!r}
PROCESS = {process!r}

PARAMS = {{}}

OBJECTS = []


def build(**p):
    return Part.Document(OBJECTS, p)
'''


def has_objects(src_or_tree) -> bool:
    tree = ast.parse(src_or_tree) if isinstance(src_or_tree, str) else src_or_tree
    return E._top_assign(tree, "OBJECTS") is not None


def names(src) -> list[str]:
    tree = ast.parse(src)
    return [n for w in ("FEATURES", "OBJECTS") for n, _ in E._entries(tree, w)[1]]


def is_part_type(t) -> bool:
    kind = E.KINDS.get(t, t)
    return isinstance(kind, str) and kind.startswith("Part.")


def goes_to_objects(op) -> bool:
    feat = op.get("feature") or {}
    return is_part_type(feat.get("type")) or op.get("list") == "OBJECTS"


def ensure_import(src: str) -> str:
    """src with `from cad_agent import feature_part as Part`, after the module's docstring and imports."""
    tree = ast.parse(src)
    for n in tree.body:
        if isinstance(n, ast.ImportFrom) and n.module == "cad_agent" and any(
                a.name == "feature_part" and a.asname == "Part" for a in n.names):
            return src
        if isinstance(n, ast.Import) and any(a.name == "cad_agent.feature_part" and a.asname == "Part"
                                             for a in n.names):
            return src
    binds = {t.id for n in ast.walk(tree) if isinstance(n, (ast.Assign, ast.AnnAssign))
             for t in (n.targets if isinstance(n, ast.Assign) else [n.target]) if isinstance(t, ast.Name)}
    binds |= {a.asname or a.name.split(".")[0] for n in tree.body if isinstance(n, (ast.Import, ast.ImportFrom))
              for a in n.names}
    if "Part" in binds or any(isinstance(n, ast.ImportFrom) and any(a.name == "*" for a in n.names)
                              for n in tree.body):
        raise E.FeatureEditError("the part file binds the name Part (or imports *), which its Part workbench objects "
                                 "need: rename it before adding Part objects")
    t = E._Text(src)
    pos = 0
    for n in tree.body:
        if isinstance(n, (ast.Import, ast.ImportFrom)) or (n is tree.body[0] and isinstance(n, ast.Expr)
                                                            and isinstance(n.value, ast.Constant)):
            pos = t.line_end(t.b(n))
        else:
            break
    return t.edit([(pos, pos, IMPORT)])


def _document_call(src):
    """The Body(FEATURES, p, ...) call of build() turned into Part.Document(OBJECTS, p, FEATURES, ...)."""
    t = E._Text(src)
    body = E._body_call(t.tree)
    if body is None or E._fname(body) != "Body" or len(body.args) < 2:
        raise E.FeatureEditError("the part's build() does not return Body(FEATURES, p, ...): add the Part objects' "
                                 "OBJECTS = [...] and `return Part.Document(OBJECTS, p, FEATURES, ...)` by hand")
    feats, params = body.args[0], body.args[1]
    head = f"Part.Document(OBJECTS, {ast.get_source_segment(src, params)}, {ast.get_source_segment(src, feats)}"
    spans = [(t.a(body), t.b(params), head)]
    after = E._top_assign(t.tree, "TIP") or E._top_assign(t.tree, "FEATURES")
    end = t.line_end(t.b(after))
    spans.append((end, end, "\n# The document's Part objects (cad_agent/feature_part.py); the Body above is \"Body\".\n"
                            "OBJECTS = [\n]\n"))
    return t.edit(spans)


def to_document(src: str) -> str:
    """A Body part file (or a hand-written one, given its Body first) with OBJECTS."""
    if has_objects(src):
        return src
    if E._top_assign(ast.parse(src), "FEATURES") is None:
        src = E._convert(src)
    return ensure_import(_document_call(src))


def add_body(src: str) -> str:
    """A document with no Body given an empty one: FEATURES = [] and TIP before OBJECTS, Part.Document taking them."""
    t = E._Text(src)
    call = E._body_call(t.tree)
    if call is None or E._fname(call) != "Part.Document":
        raise E.FeatureEditError("the part's build() does not return Part.Document(OBJECTS, p): give it its Body by "
                                 "hand")
    if len(call.args) >= 3 or any(k.arg == "features" for k in call.keywords):
        return src
    objs = E._top_assign(t.tree, "OBJECTS")
    spans = [(t.line_start(t.a(objs)), t.line_start(t.a(objs)),
              "# The PartDesign Body, \"Body\" to the objects below (cad_agent/feature.py).\nFEATURES = [\n]\n"
              "TIP = None\n\n")]
    last = call.args[-1] if call.args else None
    pos = t.b(last) if last is not None else t.b(call) - 1
    spans.append((pos, pos, ", FEATURES, tip=TIP"))
    return E.ensure_import(t.edit(spans), {"Sketch"})


def add(src: str, op: dict) -> str:
    """An "add" into OBJECTS."""
    feat = dict(op.get("feature") or {})
    src = to_document(src)
    if feat.get("name") in names(src) or feat.get("name") == "Body" and E._top_assign(ast.parse(src), "FEATURES"):
        raise E.FeatureEditError(f"there is already an object {feat.get('name')!r}")
    src = E._insert(src, E.feature_src(feat, 0), op.get("after"), "after" not in op, "OBJECTS")
    kinds = E._kinds_of(feat)
    return E.ensure_import(src, {k for k in kinds if "." not in k})


def check(src: str, d: dict):
    """The OBJECTS of an edited source: names unique over the document, each object built from its dict, each link to
    an object before it, the Body or a Body feature."""
    if "objects" not in d:
        return
    body_names = {f["name"] for f in d["features"]} | ({"BaseFeature"} if d.get("base") else set())
    seen = set(body_names) | ({"Body"} if d.get("body") else set())
    for f in d["objects"]:
        n = f["name"]
        if not E.NAME.match(n):
            raise E.FeatureEditError(f"{n!r} is not a name FreeCAD takes (letters, digits and _)")
        if n in seen or n == "Body":
            raise E.FeatureEditError(f"two objects are named {n!r}")
        try:
            kind = E.KINDS[f["type"]]
            if kind == "Sketch":
                F.Sketch(n, f.get("support") or "XY",
                         [F.geometry_from_dict(g) for g in f["geometry"]],
                         [F.constraint_from_dict(c) for c in f["constraints"]])
                if f.get("external_geometry") or (f.get("attachment_support") and not f.get("support")):
                    raise E.FeatureEditError(f"{n}: a sketch outside a Body is placed on the XY, XZ or YZ plane here")
            else:
                obj = KW.kw_class(kind).from_dict(f)
                for r in obj.references():
                    if r not in seen and r not in ("XY_Plane", "XZ_Plane", "YZ_Plane"):
                        raise E.FeatureEditError(f"{n}: it links {r!r}, which is not before it")
        except (TypeError, KeyError, F.FeatureError) as e:
            raise E.FeatureEditError(f"{n}: {e}") from None
        seen.add(n)


def tree_info(d: dict) -> dict:
    """What the tree shows of a document, from read()'s dicts: {"children": {name: the objects shown under it
    (claimChildren)}, "top": the rows at the top (what nothing claims, the Body first when it has FEATURES), "shown": the
    objects FreeCAD shows (feature_part.visible), "hidden": the rest}. An object that does not build as one is a plain
    row."""
    from . import feature_part as Part
    objs = []
    for f in d.get("objects", []):
        kind = E.KINDS.get(f["type"])
        try:
            if kind == "Sketch":
                objs.append(F.Sketch(f["name"], f.get("support") or "XY"))
            else:
                objs.append(KW.kw_class(kind).from_dict(f))
        except (TypeError, KeyError, F.FeatureError, AttributeError):
            continue
    children = {o.name: o.inputs() for o in objs if isinstance(o, Part.PartObject)}
    claimed = {c for cs in children.values() for c in cs}
    body = bool(d.get("body"))
    top = (["Body"] if body and "Body" not in claimed else []) + [o.name for o in objs if o.name not in claimed]
    shown = Part.visible(objs, [] if body else None)
    names = [o.name for o in objs if not isinstance(o, F.Sketch)] + (["Body"] if body else [])
    hid = Part.hidden_by(objs)
    sketches = [o.name for o in objs if isinstance(o, F.Sketch) and o.name not in hid]   # shown until a user hides them
    return {"children": children, "top": top, "shown": shown, "hidden": [n for n in names if n not in shown],
            "sketches_shown": sketches}


def object_shape(src: str, path, name: str):
    """(the shape of the object named name, FreeCAD's message or None) for the part module src at path, each object built
    as a recompute builds it (a failed one has no shape)."""
    import types
    from . import feature_part as Part
    mod = types.ModuleType(f"_cad_{getattr(path, 'stem', 'part')}")
    mod.__file__ = str(path)
    exec(compile(src, str(path), "exec"), mod.__dict__)
    params = dict(getattr(mod, "PARAMS", {}) or {})
    feats = getattr(mod, "FEATURES", None)
    base = mod.build_base(**params) if hasattr(mod, "build_base") else None
    tip = getattr(mod, "TIP", None)
    shapes = Part.evaluate(getattr(mod, "OBJECTS", []), params, feats, base, tip, keep_going=True)
    if name in shapes["_errors"]:
        return None, shapes["_errors"][name]
    return shapes.get(name), None


def new_document(part: str, material: str, process: str) -> str:
    return DOCUMENT_TEMPLATE.format(part=part, material=material, process=process)
