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
        as written, a number or a PARAMS name. A Pad's or Pocket's every property is there, defaults filled in;
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
from . import params as P

TYPE_IDS = {"Sketch": "Sketcher::SketchObject", "Pad": "PartDesign::Pad", "Pocket": "PartDesign::Pocket"}
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
                 "start_type": "start_type", "start_offset": "start_offset", "refine": "refine"}
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
        if isinstance(n, ast.Call) and _fname(n) == "Body":
            return n
    return None


def _fname(call):
    f = call.func
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
    d = {"type": c.type, "args": list(c.args)}
    if c.dimensional:
        d["value"] = c.value
    d["driving"], d["name"] = c.driving, c.name or ""
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


def _entries(tree):
    node = _top_assign(tree, "FEATURES")
    if node is None:
        return None, []
    if not isinstance(node.value, ast.List):
        raise FeatureEditError("FEATURES is not a list the app can edit")
    out = []
    for e in node.value.elts:
        if not (isinstance(e, ast.Call) and _fname(e) in TYPE_IDS):
            raise FeatureEditError(f"FEATURES holds {ast.unparse(e)[:60]!r}, not a Sketch, Pad or Pocket call")
        n = _arg(e, SKETCH_POS, "name")
        if not (isinstance(n, ast.Constant) and isinstance(n.value, str)):
            raise FeatureEditError("each FEATURES entry starts with its name, a string")
        out.append((n.value, e))
    return node.value, out


def _feature_dict(call, src):
    kind = _fname(call)
    if kind == "Sketch":
        d = {"name": _lit(_arg(call, SKETCH_POS, "name"), src), "type": TYPE_IDS[kind]}
        sup = _arg(call, SKETCH_POS, "support") or _arg(call, (), "plane")
        d["support"] = F._plane_key(_lit(sup, src)) if sup is not None else "XY"
        off = _arg(call, (), "attachment_offset")
        d["attachment_offset"] = _lit(off, src) if off is not None else None
        g = _arg(call, SKETCH_POS, "geometry")
        c = _arg(call, SKETCH_POS, "constraints")
        d["geometry"] = _lit(g, src) if g is not None else []
        d["constraints"] = _lit(c, src) if c is not None else []
        return d
    d = {"name": _lit(_arg(call, EXTRUDE_POS, "name"), src), "type": TYPE_IDS[kind],
         "profile": _lit(_arg(call, EXTRUDE_POS, "profile"), src)}
    kw = {k.arg: _lit(k.value, src) for k in call.keywords if k.arg != "profile"}
    unknown = set(kw) - set(EXTRUDE_PROPS.values()) - {"midplane", "taper_angle", "taper_angle2"}
    if unknown:
        raise FeatureEditError(f"{d['name']}: {', '.join(sorted(unknown))} is not a property of a {kind}")
    try:
        obj = getattr(F, kind)(d["name"], d["profile"], **kw)     # defaults, and the deprecated forms
    except (TypeError, F.FeatureError) as e:
        raise FeatureEditError(str(e)) from None
    for key, attr in EXTRUDE_PROPS.items():
        v = getattr(obj, attr)
        d[key] = list(v) if isinstance(v, tuple) else v
    for key in ("up_to_face", "up_to_face2", "up_to_shape", "up_to_shape2"):
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
    base = lst is None or (body is not None and any(k.arg == "base" for k in body.keywords))
    if tip is None and feats:
        tip = feats[-1]["name"]
    return {"part": part, "params": P.read_src(src), "base": base, "tip": tip, "features": feats}


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
    if t in F.DIMENSIONAL:
        if "value" not in c:
            raise FeatureEditError(f"a {t} constraint needs a value")
        v = c["value"]
        args.append(json.dumps(v) if isinstance(v, str) else _num(float(v)))
    if c.get("name"):
        args.append(f"name={json.dumps(c['name'])}")
    if c.get("driving") is False:
        args.append("driving=False")
    return f"Constraint({', '.join(args)})"


def _ensure_import(src: str) -> str:
    """The part file's `from cad_agent.feature import (...)` with every geometry kind its FEATURES call,
    so a sketch given an Ellipse or a BSplineCurve still imports."""
    tree = ast.parse(src)
    imp = next((n for n in tree.body if isinstance(n, ast.ImportFrom) and n.module == "cad_agent.feature"
                and not any(a.asname for a in n.names)), None)
    if imp is None or any(a.name == "*" for a in imp.names):
        return src
    have = {a.name for a in imp.names}
    used = {n.func.id for n in ast.walk(tree) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id in F.GEOMETRY}
    if used <= have:
        return src
    names = sorted(have | used, key=str.lower)
    head, pad = "from cad_agent.feature import (", " " * len("from cad_agent.feature import (")
    lines, line = [], head
    for k, n in enumerate(names):
        piece = n + (", " if k < len(names) - 1 else ")")
        if len(line) + len(piece.rstrip()) > 110 and line.strip() not in (head.strip(), ""):
            lines.append(line.rstrip())
            line = pad
        line += piece
    lines.append(line)
    t = _Text(src)
    return t.edit([(t.a(imp), t.b(imp), "\n".join(lines))])


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
    if kind == "Sketch":
        parts = [json.dumps(name), f"support={json.dumps(d.get('support') or 'XY')}"]
        if d.get("attachment_offset") is not None:
            parts.append(f"attachment_offset={lit(_tuples('attachment_offset', d['attachment_offset']))}")
        g = [geometry_src(x) for x in d.get("geometry", [])]
        c = [constraint_src(x) for x in d.get("constraints", [])]
        parts.append(f"geometry={_list_src(g, indent + 7)}")
        parts.append(f"constraints={_list_src(c, indent + 7)}")
        return "Sketch(" + (",\n" + " " * (indent + 7)).join(parts) + ")"
    if kind not in ("Pad", "Pocket"):
        raise FeatureEditError(f"a feature of type {d.get('type')!r} is not a Sketch, Pad or Pocket")
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


def _tuples(key, v):
    """A property's value from JSON as the part file writes it: points and offsets as tuples,
    ("Pad", "Face6") as a tuple, up_to_shape a list of names or (name, [faces]) tuples."""
    if key in ("attachment_offset", "direction") and isinstance(v, list):
        return tuple(tuple(x) if isinstance(x, list) else x for x in v)
    if key in ("up_to_face", "up_to_face2") and isinstance(v, list):
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


def _insert(src: str, text: str, after: str | None, at_end: bool) -> str:
    """src with a FEATURES entry (its source, continuation lines indented from column 0) put in: at the end,
    first (after None), or after the entry named after."""
    t = _Text(src)
    lst, entries = _entries(t.tree)
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
    t = _Text(src)
    lst, entries = _entries(t.tree)
    for i, (n, call) in enumerate(entries):
        if n == name:
            return t, lst, i, call
    raise FeatureEditError(f"there is no feature {name!r}")


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
            elif key == "support":
                F._plane_key(val)
                _set_arg(t, call, SKETCH_POS, "support", json.dumps(val), spans)
            elif key == "attachment_offset":
                if val is None:
                    _drop_kw(t, call, "attachment_offset", spans)
                else:
                    _set_arg(t, call, (), "attachment_offset", lit(_tuples(key, val)), spans)
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


def _refs(call):
    """The string constants of a Pad or Pocket that name other features: (node, name)."""
    out = []
    if _fname(call) == "Sketch":
        return out
    p = _arg(call, EXTRUDE_POS, "profile")
    if isinstance(p, ast.Constant):
        out.append((p, p.value))
    for k in call.keywords:
        if k.arg in ("up_to_face", "up_to_face2", "up_to_shape", "up_to_shape2"):
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
    _, entries = _entries(t.tree)
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
        if n in kinds or n == "BaseFeature":
            raise FeatureEditError(f"two features are named {n!r}")
        try:
            if f["type"] == TYPE_IDS["Sketch"]:
                F.Sketch(n, f["support"], [F.geometry_from_dict(g) for g in f["geometry"]],
                         [F.Constraint(c["type"], *c["args"], *([c["value"]] if "value" in c else []),
                                       name=c.get("name") or None, driving=c.get("driving", True))
                          for c in f["constraints"]], attachment_offset=f["attachment_offset"])
            else:
                if kinds.get(f["profile"]) != "Sketch":
                    raise FeatureEditError(f"{n}: its profile {f['profile']!r} is not a sketch before it")
                for key in ("up_to_face", "up_to_face2"):
                    r = f.get(key)
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
    return d


def apply_src(src: str, ops: list) -> str:
    for k, op in enumerate(ops):
        if not isinstance(op, dict) or "op" not in op:
            raise FeatureEditError(f"op {k} is not an edit: {op!r}")
        kind = op["op"]
        tree = ast.parse(src)
        has_list = _top_assign(tree, "FEATURES") is not None
        if kind == "add":
            feat = op.get("feature") or {}
            if not has_list:
                src = _convert(src)
            if feat.get("name") in [f["name"] for f in read_src(src)["features"]]:
                raise FeatureEditError(f"there is already a feature {feat.get('name')!r}")
            src = _insert(src, feature_src(feat, 0), op.get("after"), "after" not in op)
            continue
        if not has_list:
            raise FeatureEditError("the part has no feature list yet: add a feature first")
        name = op.get("name")
        if kind == "set":
            src = _op_set(src, name, op.get("props") or {})
        elif kind == "delete":
            users = _users(src, name)
            if users:
                raise FeatureEditError(f"{name} cannot be deleted: {', '.join(users)} uses it")
            t, lst, i, _ = _entry(src, name)
            a, b = _entry_span(t, lst, i)
            tip = read_src(src)["tip"]
            src = t.edit([(a, b, "")])
            if tip == name and _top_assign(ast.parse(src), "TIP") is not None:
                names = [f["name"] for f in read_src(src)["features"]]
                before = names[i - 1] if i else None
                src = _set_tip(src, before) if before else _set_tip(src, None)
        elif kind == "rename":
            to = op.get("to")
            if not (isinstance(to, str) and NAME.match(to)):
                raise FeatureEditError(f"{to!r} is not a name FreeCAD takes (letters, digits and _)")
            if to in [f["name"] for f in read_src(src)["features"]]:
                raise FeatureEditError(f"there is already a feature {to!r}")
            t, lst, i, call = _entry(src, name)
            spans = [(t.a(_arg(call, SKETCH_POS, "name")), t.b(_arg(call, SKETCH_POS, "name")), json.dumps(to))]
            for _, c in _entries(t.tree)[1]:
                spans += [(t.a(nd), t.b(nd), json.dumps(to)) for nd, r in _refs(c) if r == name]
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
            src = _insert(src, text, after, False)
        elif kind == "tip":
            if name is not None and name not in [f["name"] for f in read_src(src)["features"]] \
                    and name != "BaseFeature":
                raise FeatureEditError(f"there is no feature {name!r}")
            src = _set_tip(src, name)
        else:
            raise FeatureEditError(f"{kind!r} is not an edit (add, set, delete, rename, move, tip)")
        _check(src)
    src = _ensure_import(src)
    _check(src)
    return src


def apply(part_path, ops: list) -> dict:
    """Apply the ops to the part file, all or nothing, and return read() of the result."""
    path = Path(part_path)
    src = path.read_text()
    new = apply_src(src, list(ops))
    out = read_src(new, path.stem)
    if new != src:
        path.write_text(new)
    return out
