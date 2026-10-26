"""A part's feature list, read and edited in place, as params.py reads and edits its PARAMS.

The app's tree and Sketcher save every edit here, so the Python stays the source of truth: an edit rewrites the
FEATURES entries it touches and nothing else, comments and layout kept, and git shows what changed. The file
format is cad_agent/feature.py's:

    from cad_agent.feature import (ArcOfCircle, Body, Circle, Constraint, LineSegment, Pad, Pocket, Point,
                                   Sketch)

    PARAMS = {"thick": 5.0}

    FEATURES = [
        Sketch("Sketch", support="XY",
               geometry=[LineSegment((0.0, 0.0), (40.0, 0.0)), ...],
               constraints=[Constraint("Coincident", 0, 2, 1, 1), ...]),
        Pad("Pad", "Sketch", length="thick"),
    ]
    TIP = "Pad"                          # optional: Body.Tip, the last feature when absent


    def build(**p):
        return Body(FEATURES, p, tip=TIP)

A part written by hand (a build() of free-form build123d) has no FEATURES. Its first "add" converts it: its
build() is renamed build_base() and becomes the Body's BaseFeature, `return Body(FEATURES, p,
base=build_base(**p), tip=TIP)`, and the feature list goes after it.

Two entry points, for the server:

    read(part_path) -> dict
        {"part": name, "params": {name: value}, "base": bool (a hand-built BaseFeature), "tip": name or None,
         "features": [
            {"name": "Sketch", "type": "Sketcher::SketchObject", "support": "XY", "attachment_offset": None,
             "geometry": [{"type": "LineSegment", "start": [x, y], "end": [x, y], "construction": False}, ...],
             "constraints": [{"type": "DistanceX", "args": [0, 1, 0, 2], "value": "width", "driving": True,
                              "name": ""}, ...]},
            {"name": "Pad", "type": "PartDesign::Pad", "profile": "Sketch", "side_type": "One side",
             "type1": "Length", "type2": "Length", "length": "thick", "length2": 10.0, ...}]}
        Geometry is cad_agent.planegcs's form (a Point is {"type": "Point", "at": [x, y]}); a constraint's value is
        as written, a number or a PARAMS name (on writing, "expr" takes the place of "value" when given), and it has
        "active": False and "virtual_space": True when it is deactivated or in the other virtual space. A Pad's or Pocket's every property is there, defaults filled in;
        the extrusion's own Type property is "type1" (FreeCAD's Type; "type" is the object's TypeId), the part
        file's keyword type=.
    apply(part_path, ops) -> dict (what read() then returns)
        {"op": "add", "feature": {...as read() gives...}, "after": name | None}   no "after": at the end; None: first
        {"op": "set", "name": n, "props": {...}}       a sketch's props may carry "geometry" and "constraints" whole,
                                                       and only the entries that changed are rewritten
        {"op": "delete", "name": n}                    refused while a later feature uses it
        {"op": "rename", "name": n, "to": m}           the references to it are renamed too
        {"op": "move", "name": n, "after": name | None}
        {"op": "tip", "name": n}
        All or nothing: every op is applied to the text in turn, the result is read back and every feature built
        as an object (so a bad type or value is refused), and only then is the file written.

Errors are FeatureEditError, a ValueError, worded for the user.
"""
from __future__ import annotations

import ast
import json
import math
import re
from pathlib import Path

from . import feature as F
from . import feature_edit_attach as _attach
from . import feature_kw as KW
from . import feature_part as _part_objects  # noqa: F401  the Part workbench's objects in OBJECTS (feature_edit_part.py)
from . import params as P

TYPE_IDS = {"Sketch": "Sketcher::SketchObject", "Pad": "PartDesign::Pad", "Pocket": "PartDesign::Pocket"}
TYPE_IDS.update(KW.type_ids())          # every feature_kw.KwFeature: Mirrored, AdditiveBox, ... (read and written below)
KINDS = {v: k for k, v in TYPE_IDS.items()}
SKETCH_POS = ("name", "support", "geometry", "constraints")
SKETCH_KW = ("support", "attachment_offset", "map_mode", "geometry", "constraints")
EXTRUDE_POS = ("name", "profile")
# The properties of a Pad or Pocket, as read() names them, and the part file's keyword for each.
EXTRUDE_PROPS = {"side_type": "side_type", "type1": "type", "type2": "type2", "length": "length",
                 "length2": "length2", "offset": "offset", "offset2": "offset2", "reversed": "reversed",
                 "up_to_face": "up_to_face", "up_to_face2": "up_to_face2", "up_to_shape": "up_to_shape",
                 "up_to_shape2": "up_to_shape2", "use_custom_vector": "use_custom_vector",
                 "direction": "direction", "along_sketch_normal": "along_sketch_normal",
                 "start_type": "start_type", "start_offset": "start_offset", "start_reference": "start_reference",
                 "taper_angle": "taper_angle",
                 "taper_angle2": "taper_angle2", "operation": "operation", "refine": "refine",
                 "reference_axis": "reference_axis"}
IMPORT = ("from cad_agent.feature import (ArcOfCircle, ArcOfEllipse, ArcOfHyperbola, ArcOfParabola, Body, "
          "BSplineCurve,\n                               Circle, Constraint, Ellipse, LineSegment, Pad, Pocket, "
          "Point, Sketch)\n")
NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class FeatureEditError(ValueError):
    """An edit the feature list cannot take, or a part file this cannot edit safely."""


# ── reading the source ────────────────────────────────────────────────────────────────────────────────

def _top_assign(tree, name):
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return node
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == name:
            return node
    return None


def _build_def(tree):
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "build":
            return node
    return None


def _body_call(tree):
    fn = _build_def(tree)
    if fn is None:
        return None
    for n in ast.walk(fn):
        if isinstance(n, ast.Call) and _fname(n) in ("Body", "Part.Document"):    # Part.Document: a part with OBJECTS
            return n
    return None


def _fname(call):
    f = call.func
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name) and f.value.id == "Part":
        return "Part." + f.attr                     # a Part workbench object, Part.Box(...) (feature_part.py)
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else None


_CONST = {"pi": math.pi, "PI": math.pi, "True": True, "False": False, "None": None}


def _lit(node, src):
    """A literal of the file: numbers, strings, tuples, lists, arithmetic on numbers, math.pi, and the
    geometry and Constraint calls (as read() gives them)."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, (ast.Tuple, ast.List)):
        return [_lit(e, src) for e in node.elts]
    if isinstance(node, ast.Name) and node.id in _CONST:
        return _CONST[node.id]
    if isinstance(node, ast.Attribute) and node.attr == "pi":
        return math.pi
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        v = _lit(node.operand, src)
        if isinstance(v, (int, float)):
            return -v if isinstance(node.op, ast.USub) else v
    if isinstance(node, ast.BinOp):
        a, b = _lit(node.left, src), _lit(node.right, src)
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            ops = {ast.Add: a.__add__, ast.Sub: a.__sub__, ast.Mult: a.__mul__, ast.Div: a.__truediv__}
            if type(node.op) in ops:
                return float(ops[type(node.op)](b))
    if isinstance(node, ast.Call):
        name = _fname(node)
        args = [_lit(a, src) for a in node.args]
        kw = {k.arg: _lit(k.value, src) for k in node.keywords}
        if name in F.GEOMETRY:
            try:
                return getattr(F, name)(*args, **kw).as_dict()
            except (TypeError, F.FeatureError) as e:
                raise FeatureEditError(f"{ast.get_source_segment(src, node)}: {e}") from None
        if name == "Constraint":
            try:
                c = F.Constraint(*args, **kw)
            except (TypeError, F.FeatureError) as e:
                raise FeatureEditError(f"{ast.get_source_segment(src, node)}: {e}") from None
            return _constraint_dict(c)
    raise FeatureEditError(f"{ast.get_source_segment(src, node)!r} is not a value the feature list can edit")


def _constraint_dict(c):
    d = {"type": c.type, "args": list(c.args), **F.text_dict(c)}
    if c.dimensional:
        d["value"] = c.value
    d["driving"], d["name"] = c.driving, c.name or ""
    if not c.active:
        d["active"] = False
    if c.virtual_space:
        d["virtual_space"] = True
    return d


def _arg(call, pos_names, name):
    """The node of a call's argument, given by keyword or by position."""
    for k in call.keywords:
        if k.arg == name:
            return k.value
    if name in pos_names:
        i = pos_names.index(name)
        if i < len(call.args):
            return call.args[i]
    return None


def _entries(tree, which="FEATURES"):
    """The (name, call) entries of FEATURES, or of OBJECTS (the Part workbench's objects, feature_edit_part.py)."""
    node = _top_assign(tree, which)
    if node is None:
        return None, []
    if not isinstance(node.value, ast.List):
        raise FeatureEditError(f"{which} is not a list the app can edit")
    out = []
    for e in node.value.elts:
        if not (isinstance(e, ast.Call) and _fname(e) in TYPE_IDS) or (
                _fname(e).startswith("Part.") != (which == "OBJECTS") and _fname(e) != "Sketch"):
            raise FeatureEditError(f"{which} holds {ast.unparse(e)[:60]!r}, not " +
                                   ("a Part object or a Sketch call" if which == "OBJECTS" else
                                    "a Sketch, Pad or Pocket call"))
        n = _arg(e, SKETCH_POS, "name")
        if not (isinstance(n, ast.Constant) and isinstance(n.value, str)):
            raise FeatureEditError(f"each {which} entry starts with its name, a string")
        out.append((n.value, e))
    return node.value, out


def _kw_obj(call, src):
    """A feature_kw.KwFeature entry built from its call (its nested feature calls too)."""
    cls = KW.kw_class(_fname(call))
    args = [_lit(a, src) for a in call.args]
    kw = {}
    for k in call.keywords:
        if k.arg in cls.NESTED:
            elts = k.value.elts if isinstance(k.value, (ast.List, ast.Tuple)) else None
            if elts is None or not all(isinstance(e, ast.Call) and KW.kw_class(_fname(e)) for e in elts):
                raise FeatureEditError(f"{ast.get_source_segment(src, k.value)[:60]!r}: {k.arg} is a list of "
                                       "feature calls")
            kw[k.arg] = [_kw_obj(e, src) for e in elts]
        else:
            kw[k.arg] = _lit(k.value, src)
    try:
        return cls(*args, **kw)
    except (TypeError, F.FeatureError) as e:
        raise FeatureEditError(str(e)) from None


def _feature_dict(call, src):
    kind = _fname(call)
    if KW.kw_class(kind):
        return _kw_obj(call, src).as_dict()
    if kind == "Sketch":
        d = {"name": _lit(_arg(call, SKETCH_POS, "name"), src), "type": TYPE_IDS[kind]}
        d.update(_attach.sketch_dict(call, src, _lit, _arg))   # support, attachment, external geometry
        g = _arg(call, SKETCH_POS, "geometry")
        c = _arg(call, SKETCH_POS, "constraints")
        d["geometry"] = _lit(g, src) if g is not None else []
        d["constraints"] = _lit(c, src) if c is not None else []
        return d
    d = {"name": _lit(_arg(call, EXTRUDE_POS, "name"), src), "type": TYPE_IDS[kind],
         "profile": _lit(_arg(call, EXTRUDE_POS, "profile"), src)}
    kw = {k.arg: _lit(k.value, src) for k in call.keywords if k.arg != "profile"}
    unknown = set(kw) - set(EXTRUDE_PROPS.values()) - {"midplane"}
    if unknown:
        raise FeatureEditError(f"{d['name']}: {', '.join(sorted(unknown))} is not a property of a {kind}")
    try:
        obj = getattr(F, kind)(d["name"], d["profile"], **kw)     # defaults, and the deprecated forms
    except (TypeError, F.FeatureError) as e:
        raise FeatureEditError(str(e)) from None
    for key, attr in EXTRUDE_PROPS.items():
        v = getattr(obj, attr)
        d[key] = list(v) if isinstance(v, tuple) else v
    for key in ("up_to_face", "up_to_face2", "up_to_shape", "up_to_shape2", "start_reference", "reference_axis"):
        if key in kw:
            d[key] = kw[key]
    return d


def read_src(src: str, part: str = "") -> dict:
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        raise FeatureEditError(f"the part file does not parse: {e}") from None
    lst, entries = _entries(tree)
    tip_node = _top_assign(tree, "TIP")
    tip = _lit(tip_node.value, src) if tip_node is not None else None
    feats = [_feature_dict(call, src) for _, call in entries]
    body = _body_call(tree)
    objs, objects = _entries(tree, "OBJECTS")       # the Part workbench's objects (feature_edit_part.py)
    base = (lst is None and objs is None) or (body is not None and any(k.arg == "base" for k in body.keywords))
    if tip is None and feats:
        # the last feature; a datum is never a Body's Tip (Body::insertObject leaves the Tip where it was)
        tip = next((f["name"] for f in reversed(feats) if KINDS.get(f["type"]) not in _attach.DATUM_KINDS), None)
    out = {"part": part, "params": P.read_src(src), "base": base, "tip": tip, "features": feats}
    if objs is not None:
        out.update(body=lst is not None, objects=[_feature_dict(call, src) for _, call in objects])
        from . import feature_edit_part as _P
        out["object_tree"] = _P.tree_info(out)          # the tree's rows and what is shown (feature_edit_part.py)
    return out


def read(part_path) -> dict:
    """The part's feature list, as the module docstring describes it."""
    path = Path(part_path)
    return read_src(path.read_text(), path.stem)


# ── writing literals ──────────────────────────────────────────────────────────────────────────────────

def _num(v):
    if isinstance(v, bool):
        return "True" if v else "False"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        r = round(v, 9)
        return repr(0.0 if r == 0 else r)
    raise FeatureEditError(f"{v!r} is not a number")


def lit(v) -> str:
    """Python source for a value: numbers to 1e-9, strings in double quotes as the files write them."""
    if v is None or isinstance(v, (bool, int, float)):
        return "None" if v is None else _num(v)
    if isinstance(v, str):
        return json.dumps(v)
    if isinstance(v, (list, tuple)):
        inner = ", ".join(lit(x) for x in v)
        return f"({inner},)" if len(v) == 1 and isinstance(v, tuple) else f"({inner})" \
            if isinstance(v, tuple) else f"[{inner}]"
    raise FeatureEditError(f"{v!r} cannot be written in a part file")


def _pt(p):
    return f"({_num(float(p[0]))}, {_num(float(p[1]))})"


def geometry_src(g: dict) -> str:
    kind = g.get("type")
    c = ", construction=True" if g.get("construction") else ""
    try:
        if kind == "LineSegment":
            return f"LineSegment({_pt(g['start'])}, {_pt(g['end'])}{c})"
        if kind == "Circle":
            return f"Circle({_pt(g['center'])}, {_num(float(g['radius']))}{c})"
        if kind == "ArcOfCircle":
            return (f"ArcOfCircle({_pt(g['center'])}, {_num(float(g['radius']))}, "
                    f"{_num(float(g['start_angle']))}, {_num(float(g['end_angle']))}{c})")
        if kind == "Point":
            return f"Point({_pt(g['at'] if 'at' in g else g['point'])}{c})"
        if kind in F._curves.GEOMETRY:             # the conics and B-splines (feature_curves.py)
            return F._curves.source(g, _num)
    except (KeyError, TypeError, IndexError):
        raise FeatureEditError(f"geometry {g!r} is missing a coordinate") from None
    except F.FeatureError as e:
        raise FeatureEditError(str(e)) from None
    raise FeatureEditError(f"geometry type {kind!r} is not LineSegment, Circle, ArcOfCircle or Point")


def constraint_src(c: dict) -> str:
    t = c.get("type")
    args = [json.dumps(t)] + [str(int(a)) for a in c.get("args", [])]
    if t == "Text":                 # Constraint("Text", [g0, p0, ...], text, font, is_text_height): sketch_text.py
        args = [json.dumps(t), "[" + ", ".join(str(int(a)) for a in c.get("args", [])) + "]",
                json.dumps(c.get("text", ""), ensure_ascii=False), json.dumps(c.get("font", ""), ensure_ascii=False),
                "False" if c.get("is_text_height", True) is False else "True"]
    if t in F.DIMENSIONAL:
        if "value" not in c:
            raise FeatureEditError(f"a {t} constraint needs a value")
        v = c["expr"] if c.get("expr") else c["value"]   # "expr": the expression the UI binds the value to
        args.append(json.dumps(v) if isinstance(v, str) else _num(float(v)))
    if c.get("name"):
        args.append(f"name={json.dumps(c['name'])}")
    if c.get("driving") is False:
        args.append("driving=False")
    if c.get("active") is False:
        args.append("active=False")
    if c.get("virtual_space"):
        args.append("virtual_space=True")
    return f"Constraint({', '.join(args)})"


def _list_src(items, indent):
    pad = " " * indent
    if not items:
        return "[]"
    return "[\n" + "".join(f"{pad}    {i},\n" for i in items) + f"{pad}]"


def feature_src(d: dict, indent: int = 4) -> str:
    """A FEATURES entry for a feature dict as read() gives it: a Sketch(...), Pad(...) or Pocket(...) call
    with the properties that are not FreeCAD's defaults."""
    kind = KINDS.get(d.get("type"), d.get("type"))
    name = d.get("name")
    if not (isinstance(name, str) and name):
        raise FeatureEditError("a feature needs a name")
    if KW.kw_class(kind):
        try:
            return kw_src(KW.kw_class(kind).from_dict(d), indent)
        except (TypeError, F.FeatureError) as e:
            raise FeatureEditError(str(e)) from None
    if kind == "Sketch":
        parts = [json.dumps(name)] + _attach.attach_kw(_attach.merged_sketch(d), "Sketch")
        g = [geometry_src(x) for x in d.get("geometry", [])]
        c = [constraint_src(x) for x in d.get("constraints", [])]
        parts.append(f"geometry={_list_src(g, indent + 7)}")
        parts.append(f"constraints={_list_src(c, indent + 7)}")
        return "Sketch(" + (",\n" + " " * (indent + 7)).join(parts) + ")"
    if kind not in ("Pad", "Pocket"):
        raise FeatureEditError(f"a feature of type {d.get('type')!r} is not a Sketch, Pad or Pocket, or a datum")
    default = getattr(F, kind)("x", "y")
    parts = [json.dumps(name), json.dumps(d.get("profile"))]
    for key, kwname in EXTRUDE_PROPS.items():
        if key not in d:
            continue
        v = d[key]
        dv = getattr(default, kwname)
        if (list(dv) if isinstance(dv, tuple) else dv) == v:
            continue
        parts.append(f"{kwname}={lit(_tuples(key, v))}")
    unknown = set(d) - set(EXTRUDE_PROPS) - {"name", "type", "profile"}
    if unknown:
        raise FeatureEditError(f"{name}: {', '.join(sorted(unknown))} is not a property of a {kind}")
    return f"{kind}({', '.join(parts)})"


def kw_src(obj, indent: int = 4) -> str:
    """A KwFeature's call: its name, its positional properties and the keywords that are not FreeCAD's defaults; a
    nested list (MultiTransform's transformations) one call a line."""
    parts = [json.dumps(obj.name)]
    keep = set(obj.source_props()) if hasattr(obj, "source_props") else None   # a Hole: what was chosen
    skip = (lambda k: k not in keep) if keep is not None else obj.is_default
    for k in obj.POS:
        if skip(k):
            break
        parts.append(lit(obj.source_value(k)))
    for k in obj.DEFAULTS:
        if (k in obj.POS and len(parts) > 1 + obj.POS.index(k)) or skip(k):
            continue
        if k in obj.NESTED:
            parts.append(f"{k}={_list_src([kw_src(x, indent + 4) for x in getattr(obj, k)], indent)}")
        else:
            parts.append(f"{k}={lit(obj.source_value(k))}")
    return f"{obj.kind}({', '.join(parts)})"


def _tuples(key, v):
    """A property's value from JSON as the part file writes it: points and offsets as tuples,
    ("Pad", "Face6") as a tuple, up_to_shape a list of names or (name, [faces]) tuples."""
    if key in ("attachment_offset", "direction") and isinstance(v, list):
        return tuple(tuple(x) if isinstance(x, list) else x for x in v)
    if key in ("up_to_face", "up_to_face2", "start_reference", "reference_axis") and isinstance(v, list):
        return tuple(v)
    if key in ("up_to_shape", "up_to_shape2") and isinstance(v, list):
        return [tuple(r) if isinstance(r, list) else r for r in v]
    return v


# ── the text, edited by spans ─────────────────────────────────────────────────────────────────────────

class _Text:
    """The source as bytes (ast's columns are UTF-8 byte offsets), with spans from nodes."""

    def __init__(self, src: str):
        self.raw = src.encode()
        self.tree = ast.parse(src)
        self.src = src
        self.starts = [0]
        for line in self.raw.splitlines(keepends=True):
            self.starts.append(self.starts[-1] + len(line))

    def a(self, node):
        return self.starts[node.lineno - 1] + node.col_offset

    def b(self, node):
        return self.starts[node.end_lineno - 1] + node.end_col_offset

    def edit(self, spans) -> str:
        raw = self.raw
        order = sorted(range(len(spans)), key=lambda i: (spans[i][0], spans[i][1], i), reverse=True)
        for a, b, text in (spans[i] for i in order):      # inserts at one place keep their order
            raw = raw[:a] + text.encode() + raw[b:]
        return raw.decode()

    def line_start(self, pos):
        return self.raw.rfind(b"\n", 0, pos) + 1

    def line_end(self, pos):
        """After the newline that ends the line pos is on."""
        i = self.raw.find(b"\n", pos)
        return len(self.raw) if i < 0 else i + 1

    def after_comma(self, pos):
        """pos moved past spaces and one comma, if a comma follows."""
        i = pos
        while i < len(self.raw) and self.raw[i:i + 1] in (b" ", b"\t"):
            i += 1
        return i + 1 if self.raw[i:i + 1] == b"," else pos


def _entry_span(t: _Text, lst, i):
    """The bytes of FEATURES entry i with its comma: its whole lines (and a comment after it) when it sits
    on lines of its own."""
    e = lst.elts[i]
    a, b = t.a(e), t.after_comma(t.b(e))
    rest = t.raw[b:t.line_end(b)].strip()
    if t.raw[t.line_start(a):a].strip() == b"" and (rest == b"" or rest.startswith(b"#")):
        return t.line_start(a), t.line_end(b)
    while b < len(t.raw) and t.raw[b:b + 1] == b" ":
        b += 1
    return a, b


def _indent(t: _Text, lst):
    if lst.elts:
        return lst.elts[0].col_offset
    return 4


def _insert_at(t: _Text, lst, after_index):
    """The byte offset a new entry's lines go at: after entry after_index, or first when it is None."""
    if after_index is None:
        return t.line_end(t.a(lst))                 # the line after "FEATURES = ["
    e = lst.elts[after_index]
    return t.line_end(t.after_comma(t.b(e)))


def _insert(src: str, text: str, after: str | None, at_end: bool, which="FEATURES") -> str:
    """src with a FEATURES (or OBJECTS) entry (its source, continuation lines indented from column 0) put in: at the
    end, first (after None), or after the entry named after."""
    t = _Text(src)
    lst, entries = _entries(t.tree, which)
    names = [n for n, _ in entries]
    ind = _indent(t, lst)
    lines = "".join(" " * ind + line + "\n" for line in text.split("\n")).rstrip("\n") + ",\n"
    if not lst.elts:
        return t.edit([(t.a(lst), t.b(lst), "[\n" + lines + "]")])
    if at_end:
        idx = len(names) - 1
    elif after is None:
        idx = None
    elif after in names:
        idx = names.index(after)
    else:
        raise FeatureEditError(f"there is no feature {after!r} to put it after")
    spans = []
    if idx is not None:
        e = lst.elts[idx]
        end = t.after_comma(t.b(e))
        if end == t.b(e):                           # the entry had no trailing comma
            spans.append((end, end, ","))
        rest = t.raw[end:t.line_end(end)].strip()
        if rest and not rest.startswith(b"#"):      # entries that share a line: right after this one
            spans.append((end, end, " " + text.strip() + ","))
            return t.edit(spans)
    pos = _insert_at(t, lst, idx)
    spans.append((pos, pos, lines))
    return t.edit(spans)


def _entry(src, name):
    """(text, the list, index, call) of the FEATURES or OBJECTS entry named name."""
    t = _Text(src)
    for which in ("FEATURES", "OBJECTS"):
        lst, entries = _entries(t.tree, which)
        for i, (n, call) in enumerate(entries):
            if n == name:
                return t, lst, i, call
    raise FeatureEditError(f"there is no feature {name!r}")


def _which(src, name):
    """The list ("FEATURES" or "OBJECTS") that holds name, or None."""
    tree = ast.parse(src)
    for which in ("FEATURES", "OBJECTS"):
        if name in [n for n, _ in _entries(tree, which)[1]]:
            return which
    return None


def _set_arg(t: _Text, call, pos_names, kw: str, text: str, spans):
    node = _arg(call, pos_names, kw)
    if node is not None:
        spans.append((t.a(node), t.b(node), text))
        return
    last = (call.args + [k for k in call.keywords])
    last = max(last, key=lambda n: (n.end_lineno, n.end_col_offset)) if last else None
    pos = t.b(last) if last is not None else t.b(call) - 1
    spans.append((pos, pos, (", " if last is not None else "") + f"{kw}={text}"))


def _drop_kw(t: _Text, call, kw, spans):
    nodes = list(call.args) + list(call.keywords)
    for i, k in enumerate(call.keywords):
        if k.arg == kw:
            j = nodes.index(k)
            prev = nodes[j - 1] if j else None
            spans.append((t.b(prev) if prev is not None else t.a(k), t.b(k), ""))


def _set_list(t: _Text, node, items: list[str], spans, indent):
    """Rewrite a geometry or constraints list to items, touching only the entries that change."""
    if node is None or not isinstance(node, ast.List):
        return False
    old = node.elts
    if not old or not items:
        spans.append((t.a(node), t.b(node), _list_src(items, indent)))
        return True
    for i, text in enumerate(items[:len(old)]):
        if ast.get_source_segment(t.src, old[i]) != text and \
                ast.dump(ast.parse(text, mode="eval").body) != ast.dump(old[i]):
            spans.append((t.a(old[i]), t.b(old[i]), text))
    if len(items) > len(old):
        last = old[-1]
        pad = " " * last.col_offset
        end = t.after_comma(t.b(last))
        had = end != t.b(last)
        new = items[len(old):]
        if node.lineno != node.end_lineno:
            piece = "\n" + pad + (",\n" + pad).join(new) + ("," if had else "")
        else:
            piece = " " + ", ".join(new) + ("," if had else "")
        spans.append((end, end, ("" if had else ",") + piece))
    elif len(items) < len(old):
        keep = old[len(items) - 1]
        spans.append((t.after_comma(t.b(keep)), t.after_comma(t.b(old[-1])), ""))
    return True


def _op_set(src, name, props):
    t, lst, i, call = _entry(src, name)
    kind = _fname(call)
    spans = []
    props = dict(props)
    if "name" in props and props["name"] != name:
        raise FeatureEditError("a feature's name is changed with the rename op, not set")
    props.pop("name", None)
    if "type" in props and props.pop("type") != TYPE_IDS[kind]:
        raise FeatureEditError(f"{name} is a {kind}; its type cannot be changed")
    if kind == "Sketch":
        att = {k: props.pop(k) for k in list(props) if k in _attach.SKETCH_KEYS}
        if att:
            _attach.set_attachment(t, call, kind, _feature_dict(call, t.src), att, spans, _set_arg, _drop_kw,
                                   _arg, SKETCH_POS)
    if KW.kw_class(kind):
        return _kw_set(t, call, name, props, spans)
    if kind == "Sketch":
        ind = call.col_offset + 7
        for key, val in props.items():
            if key == "geometry":
                text = [geometry_src(g) for g in val]
                if not _set_list(t, _arg(call, SKETCH_POS, "geometry"), text, spans, ind):
                    _set_arg(t, call, (), "geometry", _list_src(text, ind), spans)
            elif key == "constraints":
                text = [constraint_src(c) for c in val]
                if not _set_list(t, _arg(call, SKETCH_POS, "constraints"), text, spans, ind):
                    _set_arg(t, call, (), "constraints", _list_src(text, ind), spans)
            else:
                raise FeatureEditError(f"{key} is not a property of a Sketch")
        return t.edit(spans)
    for key, val in props.items():
        if key == "profile":
            _set_arg(t, call, EXTRUDE_POS, "profile", json.dumps(val), spans)
            continue
        if key not in EXTRUDE_PROPS:
            raise FeatureEditError(f"{key} is not a property of a {kind}")
        kw = EXTRUDE_PROPS[key]
        if key == "side_type":
            _drop_kw(t, call, "midplane", spans)
        _set_arg(t, call, (), kw, lit(_tuples(key, val)), spans)
    return t.edit(spans)


def _kw_set(t, call, name, props, spans):
    """set on a KwFeature: each property rewritten in place, added when it was left out, and left out again when it
    goes back to FreeCAD's default."""
    cls = KW.kw_class(_fname(call))
    pos = ("name",) + cls.POS
    bare = KW.bare(cls, name)
    props = {cls.prop_of(k): v for k, v in props.items()}
    keep_defaults = hasattr(cls, "set_props")
    if keep_defaults:                           # a Hole: a value the others give is left out, a chosen one stays
        have = {k.arg: _lit(k.value, t.src) for k in call.keywords}
        try:
            props, drop = cls.set_props(have, props)
        except F.FeatureError as e:
            raise FeatureEditError(str(e)) from None
        for key in drop:
            _drop_kw(t, call, key, spans)
    for key in props:
        for d in cls.SET_DROPS.get(key, ()):
            _drop_kw(t, call, d, spans)
    for key, val in props.items():
        if key not in cls.DEFAULTS:
            raise FeatureEditError(f"{key} is not a property of a {cls.kind}")
        try:
            v = bare.normalize(key, [KW.nested_from_dict(x) for x in val or []] if key in cls.NESTED else val)
            default = bare.normalize(key, cls.DEFAULTS[key])
        except F.FeatureError as e:
            raise FeatureEditError(str(e)) from None
        node = _arg(call, pos, key)
        if v == default and key not in cls.POS and not keep_defaults:
            if node is not None:
                _drop_kw(t, call, key, spans)
        elif key in cls.NESTED:
            _set_arg(t, call, pos, key, _list_src([kw_src(x, call.col_offset + 4) for x in v], call.col_offset),
                     spans)
        else:
            _set_arg(t, call, pos, key, lit(bare.source_value(key, v)), spans)
    return t.edit(spans)


def _refs(call):
    """The string constants of a Pad or Pocket that name other features: (node, name)."""
    out = []
    if _fname(call) == "Sketch":
        return _attach.ref_nodes(call, _fname(call))
    if KW.kw_class(_fname(call)):
        cls = KW.kw_class(_fname(call))
        for key in cls.REFS:
            v = _arg(call, ("name",) + cls.POS, key)
            for e in (v.elts if isinstance(v, ast.List) or (isinstance(v, ast.Tuple) and cls.is_ref_list(key))
                      else [v] if v is not None else []):
                e = e.elts[0] if isinstance(e, (ast.Tuple, ast.List)) and e.elts else e
                if isinstance(e, ast.Constant) and isinstance(e.value, str):
                    out.append((e, e.value))
        for key in cls.NESTED:
            v = _arg(call, ("name",) + cls.POS, key)
            for e in (v.elts if isinstance(v, (ast.List, ast.Tuple)) else []):
                if isinstance(e, ast.Call):
                    out += _refs(e)
        return out
    p = _arg(call, EXTRUDE_POS, "profile")
    if isinstance(p, ast.Constant):
        out.append((p, p.value))
    for k in call.keywords:
        if k.arg in ("up_to_face", "up_to_face2", "up_to_shape", "up_to_shape2", "start_reference", "reference_axis"):
            v = k.value
            if isinstance(v, ast.Constant):
                out.append((v, v.value))
            elif isinstance(v, (ast.Tuple, ast.List)):
                firsts = [v.elts[0]] if isinstance(v, ast.Tuple) else \
                    [e.elts[0] if isinstance(e, (ast.Tuple, ast.List)) and e.elts else e for e in v.elts]
                for f in firsts:
                    if isinstance(f, ast.Constant) and isinstance(f.value, str):
                        out.append((f, f.value))
    return out


def _users(src, name):
    t = _Text(src)
    entries = _entries(t.tree)[1] + _entries(t.tree, "OBJECTS")[1]     # a Part object may use a Body's sketch
    return [n for n, call in entries if any(r == name for _, r in _refs(call))]


def _set_tip(src, name):
    t = _Text(src)
    lst, entries = _entries(t.tree)
    tip = _top_assign(t.tree, "TIP")
    spans = []
    if tip is not None:
        spans.append((t.a(tip.value), t.b(tip.value), lit(name)))
    else:
        assign = _top_assign(t.tree, "FEATURES")
        end = t.line_end(t.b(assign))
        spans.append((end, end, f"TIP = {lit(name)}\n"))
    body = _body_call(t.tree)
    if body is not None and not any(k.arg == "tip" for k in body.keywords):
        _set_arg(t, body, (), "tip", "TIP", spans)
    return t.edit(spans)


def _kinds_of(d: dict) -> set:
    """The cad_agent.feature names a feature dict's source calls (its nested features' too)."""
    kind = KINDS.get(d.get("type"), d.get("type"))
    out = {kind} if kind in F.FEATURES else set()
    cls = KW.kw_class(kind)
    for key in (cls.NESTED if cls else ()):
        for x in d.get(key) or []:
            out |= _kinds_of(x.as_dict() if isinstance(x, KW.KwFeature) else x)
    return out


def ensure_import(src: str, names) -> str:
    """src with `from cad_agent.feature import (...)` naming every one of names: the import rewritten in sorted order
    when one is missing, or added after the module's docstring and imports when the file has none."""
    tree = ast.parse(src)
    node = next((n for n in tree.body if isinstance(n, ast.ImportFrom) and n.module == "cad_agent.feature"
                 and n.level == 0 and not any(a.asname for a in n.names)), None)
    have = {a.name for a in node.names} if node is not None else set()
    names = {n for n in names if "." not in n}      # Part.Box is feature_part's (feature_edit_part.ensure_import)
    if set(names) <= have or "*" in have:
        return src
    want = sorted(have | set(names), key=lambda x: (x.lower(), x))
    head = "from cad_agent.feature import ("
    lines, line = [], head
    for i, n in enumerate(want):
        piece = n + (", " if i < len(want) - 1 else ")")
        if len(line) + len(piece.rstrip()) > 120:
            lines.append(line.rstrip())
            line = " " * len(head)
        line += piece
    text = "\n".join(lines + [line]) + "\n"
    t = _Text(src)
    if node is not None:
        return t.edit([(t.line_start(t.a(node)), t.line_end(t.b(node)), text)])
    pos = 0
    for n in tree.body:
        if isinstance(n, (ast.Import, ast.ImportFrom)) or (n is tree.body[0] and isinstance(n, ast.Expr)
                                                            and isinstance(n.value, ast.Constant)):
            pos = t.line_end(t.b(n))
        else:
            break
    return t.edit([(pos, pos, text)])


def _convert(src):
    """A hand-written part, its build() becoming the BaseFeature under an empty feature list."""
    tree = ast.parse(src)
    fn = _build_def(tree)
    if fn is None:
        raise FeatureEditError("the part has no build() to put features on")
    if any(isinstance(n, ast.FunctionDef) and n.name == "build_base" for n in tree.body):
        raise FeatureEditError("the part already has a build_base(); rename it before adding features")
    t = _Text(src)
    spans = []
    head = t.a(fn) + len("def ")
    spans.append((head, head + len("build"), "build_base"))
    for n in ast.walk(tree):                            # build() calling itself goes on calling the base
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "build":
            spans.append((t.a(n.func), t.b(n.func), "build_base"))
    # the import goes after the docstring and the imports at the top
    pos = 0
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)) or (
                isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str) and node is tree.body[0]):
            pos = t.line_end(t.b(node))
        else:
            break
    spans.append((pos, pos, IMPORT))
    tail = ("\n\n# The feature list, FreeCAD's PartDesign Body; build_base() above is its BaseFeature.\n"
            "FEATURES = [\n]\nTIP = None\n\n\ndef build(**p):\n"
            "    return Body(FEATURES, p, base=build_base(**p), tip=TIP)\n")
    end = len(t.raw)
    out = t.edit(spans)
    return out.rstrip("\n") + "\n" + tail if end else tail


def _check(src):
    """The edited source read back, every feature built as an object, the order and references sound."""
    try:
        compile(src, "<part>", "exec")
    except SyntaxError as e:
        raise FeatureEditError(f"the edit would not leave valid Python: {e}") from None
    d = read_src(src)
    seen = {"BaseFeature"} if d["base"] else set()
    kinds = {}
    for f in d["features"]:
        n = f["name"]
        if not NAME.match(n):
            raise FeatureEditError(f"{n!r} is not a name FreeCAD takes (letters, digits and _)")
        if n in kinds or n == "BaseFeature" or (n == "Body" and "objects" in d):
            raise FeatureEditError(f"two features are named {n!r}")
        try:
            if KINDS[f["type"]] in _attach.DATUM_KINDS or f["type"] == TYPE_IDS["Sketch"]:
                for r in _attach.referenced(f):
                    if r not in seen:
                        raise FeatureEditError(f"{n}: it is attached to or projects {r!r}, which is not before it")
            if KW.kw_class(KINDS.get(f["type"])):          # a datum too (feature_attach._Datum)
                obj = KW.kw_class(KINDS[f["type"]]).from_dict(f)
                for r in obj.references():
                    if r not in seen and r not in KW.ORIGIN:
                        raise FeatureEditError(f"{n}: it references {r!r}, which is not before it")
                for sub in obj.nested_names():
                    if sub in kinds or sub == n or sub in seen or not NAME.match(sub):
                        raise FeatureEditError(f"{n}: {sub!r} is not a name its transformation can take "
                                               "(two features are named so, or it is not letters, digits and _)")
                    kinds[sub] = "nested"
            elif f["type"] == TYPE_IDS["Sketch"]:
                F.Sketch(n, None, [F.geometry_from_dict(g) for g in f["geometry"]],
                         [F.constraint_from_dict(c) for c in f["constraints"]], **_attach.build(f, "Sketch"),
                         external_geometry=[tuple(r) for r in f.get("external_geometry") or []])
            else:
                if kinds.get(f["profile"]) != "Sketch":
                    raise FeatureEditError(f"{n}: its profile {f['profile']!r} is not a sketch before it")
                for key in ("up_to_face", "up_to_face2", "start_reference", "reference_axis"):
                    r = f.get(key)
                    if isinstance(r, str) and not r.endswith("_Plane") and r not in seen:
                        raise FeatureEditError(f"{n}: its {key} names {r!r}, which is not before it")
                    if isinstance(r, list) and r and r[0] not in seen:
                        raise FeatureEditError(f"{n}: its {key} names {r[0]!r}, which is not before it")
                for key in ("up_to_shape", "up_to_shape2"):
                    for r in (f.get(key) or []):
                        r0 = r if isinstance(r, str) else r[0]
                        if not str(r0).endswith("_Plane") and r0 not in seen:
                            raise FeatureEditError(f"{n}: its {key} names {r0!r}, which is not before it")
        except (TypeError, KeyError, F.FeatureError) as e:
            raise FeatureEditError(f"{n}: {e}") from None
        kinds[n] = KINDS[f["type"]]
        seen.add(n)
    if d["tip"] is not None and d["tip"] not in kinds and d["tip"] != "BaseFeature":
        raise FeatureEditError(f"the tip {d['tip']!r} is not a feature")
    from . import feature_edit_part as _P
    _P.check(src, d)                                # OBJECTS, the Part workbench's objects
    return d


def _sketch_of(src: str, name):
    """The feature.Sketch named `name` in src's FEATURES, or None."""
    for f in read_src(src)["features"]:
        if f["name"] == name and f["type"] == TYPE_IDS["Sketch"]:
            try:
                return F.Sketch(name, f["support"], [F.geometry_from_dict(g) for g in f["geometry"]],
                                attachment_offset=f["attachment_offset"])
            except (TypeError, KeyError, F.FeatureError):
                return None
    return None


def resolve_feature(part_path, feature: dict, through_all: float | None = None) -> dict:
    """A feature dict (as read() gives one, or the properties a task panel has chosen so far) with every property as
    FreeCAD's would hold it: what FreeCAD's command sets on a new one (CmdPartDesignRevolution's axis and Reversed),
    and the values that follow from the others (a Hole's diameter from its thread). Writes nothing. through_all is
    ProfileBased::getThroughAllLength when the caller knows it (a Hole's ThroughAll depth)."""
    src = Path(part_path).read_text()
    cls = KW.kw_class(KINDS.get(feature.get("type"), feature.get("type")))
    if cls is None:
        raise FeatureEditError(f"a feature of type {feature.get('type')!r} has nothing to resolve")
    feat = dict(feature)
    if feat.get("name") not in [f["name"] for f in read_src(src)["features"]] and hasattr(cls, "command_defaults"):
        feat = cls.command_defaults(feat, _sketch_of(src, feat.get("profile")))
    try:
        if hasattr(cls, "resolved"):
            return {"name": feat.get("name"), "type": cls.TYPE_ID, "profile": feat.get("profile"),
                    **cls.resolved(feat, through_all)}
        return cls.from_dict({**feat, "name": feat.get("name") or cls.kind}).as_dict()
    except (TypeError, F.FeatureError) as e:
        raise FeatureEditError(str(e)) from None


def apply_src(src: str, ops: list) -> str:
    for k, op in enumerate(ops):
        if not isinstance(op, dict) or "op" not in op:
            raise FeatureEditError(f"op {k} is not an edit: {op!r}")
        kind = op["op"]
        tree = ast.parse(src)
        has_list = _top_assign(tree, "FEATURES") is not None
        from . import feature_edit_part as _P
        if kind == "add" and _P.goes_to_objects(op):     # a Part object, or a sketch outside the Body: OBJECTS
            src = _P.add(src, op)
            _check(src)
            continue
        if kind == "add":
            feat = op.get("feature") or {}
            if not has_list:
                src = _P.add_body(src) if _P.has_objects(tree) else _convert(src)
            if feat.get("name") in _P.names(src) + ["Body"] * _P.has_objects(src):
                raise FeatureEditError(f"there is already a feature {feat.get('name')!r}")
            cls = KW.kw_class(KINDS.get(feat.get("type"), feat.get("type")))
            if hasattr(cls, "command_defaults"):    # what FreeCAD's command sets on a new one (CmdPartDesignRevolution)
                feat = cls.command_defaults(feat, _sketch_of(src, feat.get("profile")))
            src = _insert(src, feature_src(feat, 0), op.get("after"), "after" not in op)
            src = ensure_import(src, _kinds_of(feat))
            continue
        if not has_list and not _P.has_objects(tree):
            raise FeatureEditError("the part has no feature list yet: add a feature first")
        name = op.get("name")
        which = _which(src, name) if kind in ("delete", "move") else None
        if kind == "set":
            src = _op_set(src, name, op.get("props") or {})
        elif kind == "delete":
            if op.get("break"):              # Std_Delete answered Yes: links break as FreeCAD's (feature_delete.py)
                from .feature_delete import break_links
                src = break_links(src, name)
            users = _users(src, name)
            if users:
                raise FeatureEditError(f"{name} cannot be deleted: {', '.join(users)} uses it")
            t, lst, i, _ = _entry(src, name)
            a, b = _entry_span(t, lst, i)
            tip = read_src(src)["tip"]
            src = t.edit([(a, b, "")])
            if which == "FEATURES" and tip == name and _top_assign(ast.parse(src), "TIP") is not None:
                names = [f["name"] for f in read_src(src)["features"]]
                before = names[i - 1] if i else None
                src = _set_tip(src, before) if before else _set_tip(src, None)
        elif kind == "rename":
            to = op.get("to")
            if not (isinstance(to, str) and NAME.match(to)):
                raise FeatureEditError(f"{to!r} is not a name FreeCAD takes (letters, digits and _)")
            if to in _P.names(src) or to == "Body" and _P.has_objects(src):
                raise FeatureEditError(f"there is already a feature {to!r}")
            t, lst, i, call = _entry(src, name)
            spans = [(t.a(_arg(call, SKETCH_POS, "name")), t.b(_arg(call, SKETCH_POS, "name")), json.dumps(to))]
            for _, c in _entries(t.tree)[1] + _entries(t.tree, "OBJECTS")[1]:
                spans += [(t.a(nd), t.b(nd), json.dumps(to + nd.value[len(r):]))   # "LCS.XY_Plane" keeps its role
                          for nd, r in _refs(c) if r == name]
            tip = _top_assign(t.tree, "TIP")
            if tip is not None and isinstance(tip.value, ast.Constant) and tip.value.value == name:
                spans.append((t.a(tip.value), t.b(tip.value), json.dumps(to)))
            src = t.edit(spans)
        elif kind == "move":
            after = op.get("after")
            if after == name:
                raise FeatureEditError(f"{name} cannot go after itself")
            t, lst, i, call = _entry(src, name)
            a, b = _entry_span(t, lst, i)
            ind = _indent(t, lst)
            text = t.raw[t.a(call):t.b(call)].decode()
            text = "\n".join(line[ind:] if line[:ind].strip() == "" else line
                             for line in text.split("\n"))     # continuation lines from column 0
            src = t.edit([(a, b, "")])
            src = _insert(src, text, after, False, which)
        elif kind == "tip":
            if name is not None and name not in [f["name"] for f in read_src(src)["features"]] \
                    and name != "BaseFeature":
                raise FeatureEditError(f"there is no feature {name!r}")
            src = _set_tip(src, name)
        else:
            raise FeatureEditError(f"{kind!r} is not an edit (add, set, delete, rename, move, tip)")
        _check(src)
    # the geometry kinds the sketches call (an Ellipse, a BSplineCurve given by a `set`) imported as well
    src = ensure_import(src, {n.func.id for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Call)
                              and isinstance(n.func, ast.Name) and n.func.id in F.GEOMETRY})
    _check(src)
    return src


def apply(part_path, ops: list) -> dict:
    """Apply the ops to the part file, all or nothing, and return read() of the result."""
    path = Path(part_path)
    src = path.read_text()
    new = apply_src(src, list(ops))
    new = follow_src(src, new, path)
    out = read_src(new, path.stem)
    if new != src:
        path.write_text(new)
    return out


# ── names that an edit renumbered, followed (FreeCAD's topological naming) ─────────────────────────────

def _run(src: str, path: Path):
    """The part module's FEATURES, PARAMS and BaseFeature solid, run from src as state._load_module runs it."""
    import types
    mod = types.ModuleType(f"_cad_{path.stem}")
    mod.__file__ = str(path)
    exec(compile(src, str(path), "exec"), mod.__dict__)
    params = dict(getattr(mod, "PARAMS", {}) or {})
    base = mod.build_base(**params) if hasattr(mod, "build_base") else None
    return list(getattr(mod, "FEATURES", []) or []), params, base


def follow_src(before: str, after: str, path) -> str:
    """after, with each dress-up's Base renamed where the edit renumbered its base's elements or moved the
    solid before it (cad_agent.feature_dressup.follow). The source is unchanged when there is no dress-up, or
    when either side does not run."""
    if before == after:
        return after
    try:
        kinds = {f["type"] for f in read_src(after)["features"]}
    except FeatureEditError:
        return after
    from . import feature_dressup as D
    if not kinds & {c.TYPE_ID for c in D.DRESSUPS.values()}:
        return after
    try:
        fb, pb, bb = _run(before, Path(path))
        fa, pa, ba = _run(after, Path(path))
        moved = D.follow(fb, fa, pb, pa, bb, ba)
    except Exception:              # a part that does not run: its build says why, not this
        return after
    for name, (obj, subs) in moved.items():
        after = _op_set(after, name, {"base": [obj, subs]})
    if moved:
        _check(after)
    return after
