# SPDX-License-Identifier: LGPL-2.1-or-later
# Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
# LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
#   src/App/Expression.cpp: 2015 Eivind Kvedalen
#   src/App/ObjectIdentifier.cpp: 2015 Eivind Kvedalen
"""FreeCAD's expression language for the server, by the page's own engine: ui/src/expr.ts (App/Expression.l, Expression.y,
Expression.cpp at FreeCAD main 3160daf1e2b6) bundled into fcexpr_engine.js (ui/scripts/fcexprjs.py) and run in V8 through
mini-racer. There is one formula engine: what the browser computes, the server computes. This module holds only the
glue: the tree as Python dataclasses (the shapes of expr.ts's Node, so a spreadsheet can walk and rewrite it as
FreeCAD's ExpressionVisitors do), the values as Python's, and the document's hooks, which run here before a call.

    parse(text, names, owner, resolve_ambiguity=None) -> a tree (Num, Const, UnitNode, Str, Var, Neg, Pos, Op, Fn, Cond, Range)
    to_text(node)                    -> Expression::toString
    evaluate(node, Env(vars, ...))   -> a Python value (int, float, bool, str, None, complex, list, tuple, Quantity, Vector, Other)
    evaluate_value(text, env)        -> parse and evaluate
    identifiers(node)                -> every VarPath the tree reads (ranges expanded to their cells)

Env.resolve (another object's property) and Env.range_cells (a sheet's cells) are asked here for every name and range the
tree holds, and their answers (or the errors they raise) go with the call; expr.ts uses one where FreeCAD would look."""
import copy as _copy
import json
import math
import re
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

__all__ = ["ExprError", "QuantityError", "Quantity", "Vector", "Other", "QUIRKS",
           "Num", "Const", "UnitNode", "Str", "Var", "Neg", "Pos", "Op", "Fn", "Cond", "Range", "Node",
           "Ref", "VarPath", "IdAttr", "IdIndex", "IdKey", "IdRange", "ExprAttr", "ExprIndex",
           "parse", "parse_unit", "is_token_a_unit", "is_token_a_constant", "to_text", "Env", "evaluate", "evaluate_value",
           "identifiers", "walk", "copy", "range_cells", "string_to_address", "column_name", "user_string", "to_number", "py_str"]

ENGINE = Path(__file__).with_name("fcexpr_engine.js")


# ─── Errors and values ────────────────────────────────────────────────────────────────────────────

class QuantityError(Exception):
    """A parse failure ('syntax'), Base::UnitsMismatchError ('mismatch') or another evaluation error ('eval')."""

    def __init__(self, message, kind="syntax"):
        super().__init__(message)
        self.message = message
        self.kind = kind

    def __str__(self):
        return self.message


class ExprError(QuantityError):
    """An exception as Python reports it: `etype` is the class name FreeCAD raises (ParserError, TypeError, ExpressionError ...),
    `message` its text."""

    def __init__(self, message, etype, kind="eval"):
        super().__init__(message, kind)
        self.etype = etype

    def __repr__(self):
        return f"ExprError({self.message!r}, {self.etype!r})"


class Quantity:
    """Base::Quantity: a value in internal units and the eight exponents of its unit."""
    __slots__ = ("value", "dims")

    def __init__(self, value, dims=(0,) * 8):
        self.value = float(value)
        self.dims = tuple(dims)

    def __eq__(self, other):
        return isinstance(other, Quantity) and (self.value, self.dims) == (other.value, other.dims)

    def __hash__(self):
        return hash((self.value, self.dims))

    def __repr__(self):
        return py_str(self)


class Vector:
    """Base.Vector, a point or direction in mm."""
    __slots__ = ("x", "y", "z")

    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x, self.y, self.z = float(x), float(y), float(z)

    @property
    def v(self):
        return (self.x, self.y, self.z)

    def __iter__(self):
        return iter(self.v)

    def __eq__(self, other):
        return isinstance(other, Vector) and self.v == other.v

    def __hash__(self):
        return hash(self.v)

    def __repr__(self):
        return py_str(self)


class Other:
    """Something Python prints but the engine cannot compute with (a Unit, a bound method ...)."""
    __slots__ = ("type", "str")

    def __init__(self, type, str):   # noqa: A002
        self.type = type
        self.str = str

    def __repr__(self):
        return self.str

    def __eq__(self, other):
        return isinstance(other, Other) and (self.type, self.str) == (other.type, other.str)

    def __hash__(self):
        return hash((self.type, self.str))


# ─── The tree: expr.ts's Node, as dataclasses ────────────────────────────────────────────────────

@dataclass
class Ref:
    """A name as the grammar reads it (a document or an object): `str` when it was written as <<text>>."""
    name: str
    str: bool = False


@dataclass
class IdAttr:
    name: str


@dataclass
class IdIndex:
    i: int


@dataclass
class IdKey:
    key: str


@dataclass
class IdRange:
    b: int
    e: Optional[int]
    s: int = 1


IdComp = Union[IdAttr, IdIndex, IdKey, IdRange]


@dataclass
class VarPath:
    """ObjectIdentifier (expr.ts's VarPath). forced, owner_named, plain: set by a document's resolve_ambiguity."""
    doc: Optional[Ref] = None
    obj: Optional[Ref] = None
    local: bool = False
    names: list = field(default_factory=list)
    sub: list = field(default_factory=list)
    forced: bool = False
    owner_named: bool = False
    plain: bool = False


@dataclass
class ExprAttr:
    name: str


@dataclass
class ExprIndex:
    e1: Optional["Node"] = None
    e2: Optional["Node"] = None
    e3: Optional["Node"] = None
    range: bool = False


@dataclass
class Num:
    v: float


@dataclass
class Const:
    name: str
    v: float


@dataclass
class UnitNode:
    q: Quantity
    s: str


@dataclass
class Str:
    s: str
    bad: Optional[str] = None


@dataclass
class Var:
    path: VarPath
    comps: list = field(default_factory=list)


@dataclass
class Neg:
    a: "Node"


@dataclass
class Pos:
    a: "Node"


@dataclass
class Op:
    op: str
    l: "Node"   # noqa: E741
    r: "Node"


@dataclass
class Fn:
    f: str
    name: str
    args: list


@dataclass
class Cond:
    c: "Node"
    t: "Node"
    f: "Node"


@dataclass
class Range:
    a: str
    b: str


Node = Union[Num, Const, UnitNode, Str, Var, Neg, Pos, Op, Fn, Cond, Range]


# ─── The engine ──────────────────────────────────────────────────────────────────────────────────

_lock = threading.RLock()
_ctx = None


def _engine():
    global _ctx
    if _ctx is None:
        from py_mini_racer import MiniRacer   # imported on first use: the CLI's parser never loads V8
        ctx = MiniRacer()
        ctx.eval(ENGINE.read_text(encoding="utf-8"))
        _ctx = ctx
    return _ctx


def _big_int(s):
    try:
        return int(s)
    except ValueError:   # more digits than Python's default limit for str -> int
        old = sys.get_int_max_str_digits()
        sys.set_int_max_str_digits(0)
        try:
            return int(s)
        finally:
            sys.set_int_max_str_digits(old)


def _hook(o):
    if len(o) == 1:
        if "$i" in o:
            return _big_int(o["$i"])
        if "$f" in o:
            return {"nan": math.nan, "inf": math.inf, "-inf": -math.inf, "-0": -0.0}[o["$f"]]
    return o


def _f(x):
    """A float as the engine's JSON carries it."""
    x = float(x)
    if math.isnan(x):
        return {"$f": "nan"}
    if math.isinf(x):
        return {"$f": "inf" if x > 0 else "-inf"}
    if x == 0 and math.copysign(1.0, x) < 0:
        return {"$f": "-0"}
    return x


def _int_text(v):
    try:
        return str(v)
    except ValueError:
        old = sys.get_int_max_str_digits()
        sys.set_int_max_str_digits(0)
        try:
            return str(v)
        finally:
            sys.set_int_max_str_digits(old)


def _call(name, *args):
    with _lock:
        out = _engine().call("FCExpr." + name, *args)
    r = json.loads(out, object_hook=_hook)
    if "ok" in r:
        return r["ok"]
    if r["etype"] == "QuantityError":
        raise QuantityError(r["error"], r.get("kind") or "eval")
    if r["etype"] == "Crash":
        raise RuntimeError(f"the formula engine failed: {r['error']}")
    raise ExprError(r["error"], r["etype"], r.get("kind") or "eval")


def _dumps(x):
    return json.dumps(x, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


class _Quirks:
    """expr-py.ts's QUIRKS. int32_cast: FreeCAD's integral doubles above INT_MAX come out as -2147483648 (on for exprdiff)."""

    def __init__(self):
        self.__dict__["_int32"] = False

    @property
    def int32_cast(self):
        return self._int32

    def __setattr__(self, name, value):
        if name != "int32_cast":
            raise AttributeError(name)
        _call("setInt32Cast", bool(value))
        self.__dict__["_int32"] = bool(value)


QUIRKS = _Quirks()


# ── values: Python's <-> expr-py.ts's PyVal ──
def value_to_js(v):
    t = type(v)
    if v is None:
        return {"t": "none"}
    if t is bool:
        return {"t": "bool", "v": v}
    if t is int:
        return {"t": "int", "v": {"$i": _int_text(v)}}
    if t is float:
        return {"t": "float", "v": _f(v)}
    if t is complex:
        return {"t": "complex", "re": _f(v.real), "im": _f(v.imag)}
    if t is str:
        return {"t": "str", "v": v}
    if isinstance(v, Quantity):
        return {"t": "qty", "q": {"value": _f(v.value), "dims": list(v.dims)}}
    if t in (list, tuple):
        return {"t": t.__name__, "v": [value_to_js(x) for x in v]}
    if isinstance(v, Vector):
        return {"t": "vector", "v": [_f(x) for x in v.v]}
    if isinstance(v, Other):
        return {"t": "obj", "type": v.type, "str": v.str}
    raise TypeError(f"not a formula value: {v!r}")


def value_from_js(j):
    t = j["t"]
    if t == "none":
        return None
    if t in ("bool", "str"):
        return j["v"]
    if t == "int":
        return j["v"] if isinstance(j["v"], int) else _big_int(j["v"])
    if t == "float":
        return float(j["v"])
    if t == "complex":
        return complex(j["re"], j["im"])
    if t == "qty":
        return Quantity(j["q"]["value"], j["q"]["dims"])
    if t == "list":
        return [value_from_js(x) for x in j["v"]]
    if t == "tuple":
        return tuple(value_from_js(x) for x in j["v"])
    if t == "vector":
        return Vector(*j["v"])
    return Other(j["type"], j["str"])


# ── the tree: dataclasses <-> expr.ts's Node ──
def _ref_js(r):
    return None if r is None else {"name": r.name, "str": r.str}


def _idc_js(c):
    t = type(c)
    if t is IdAttr:
        return {"k": "attr", "name": c.name}
    if t is IdIndex:
        return {"k": "array", "i": c.i}
    if t is IdKey:
        return {"k": "map", "key": c.key}
    return {"k": "range", "b": c.b, "e": c.e, "s": c.s}


def _path_js(p, ids=None):
    out = {"doc": _ref_js(p.doc), "obj": _ref_js(p.obj), "local": p.local, "names": list(p.names), "sub": [_idc_js(c) for c in p.sub]}
    if p.forced:
        out["forced"] = True
    if p.owner_named:
        out["ownerNamed"] = True
    if p.plain:
        out["plain"] = True
    if ids is not None and id(p) in ids:
        out["id"] = ids[id(p)]
    return out


def node_to_js(n, ids=None):
    """A tree as expr.ts's JSON; `ids` (id(path or Range) -> number) stamps what the env's tables answer."""
    t = type(n)
    if t is Num:
        return {"k": "num", "v": _f(n.v)}
    if t is Const:
        return {"k": "const", "name": n.name, "v": _f(n.v)}
    if t is UnitNode:
        return {"k": "unit", "q": {"value": _f(n.q.value), "dims": list(n.q.dims)}, "s": n.s}
    if t is Str:
        return {"k": "str", "s": n.s, **({"bad": n.bad} if n.bad else {})}
    if t is Var:
        comps = []
        for c in n.comps:
            if type(c) is ExprAttr:
                comps.append({"name": c.name})
            else:
                comps.append({"e1": None if c.e1 is None else node_to_js(c.e1, ids), "e2": None if c.e2 is None else node_to_js(c.e2, ids),
                              "e3": None if c.e3 is None else node_to_js(c.e3, ids), "range": c.range})
        return {"k": "var", "path": _path_js(n.path, ids), "comps": comps}
    if t is Neg or t is Pos:
        return {"k": "neg" if t is Neg else "pos", "a": node_to_js(n.a, ids)}
    if t is Op:
        return {"k": "op", "op": n.op, "l": node_to_js(n.l, ids), "r": node_to_js(n.r, ids)}
    if t is Fn:
        return {"k": "fn", "f": n.f, "name": n.name, "args": [node_to_js(a, ids) for a in n.args]}
    if t is Cond:
        return {"k": "cond", "c": node_to_js(n.c, ids), "t": node_to_js(n.t, ids), "f": node_to_js(n.f, ids)}
    if t is Range:
        out = {"k": "range", "a": n.a, "b": n.b}
        if ids is not None and id(n) in ids:
            out["id"] = ids[id(n)]
        return out
    raise TypeError(f"not a formula tree: {n!r}")


def _ref_py(j):
    return None if j is None else Ref(j["name"], bool(j["str"]))


def _idc_py(j):
    k = j["k"]
    if k == "attr":
        return IdAttr(j["name"])
    if k == "array":
        return IdIndex(int(j["i"]))
    if k == "map":
        return IdKey(j["key"])
    return IdRange(int(j["b"]), None if j["e"] is None else int(j["e"]), int(j["s"]))


def node_from_js(j, deferred=None):
    """expr.ts's JSON as a tree; a path the parse left to the caller (`amb`) goes to `deferred` with what was written."""
    k = j["k"]
    if k == "num":
        return Num(float(j["v"]))
    if k == "const":
        return Const(j["name"], float(j["v"]))
    if k == "unit":
        return UnitNode(Quantity(j["q"]["value"], j["q"]["dims"]), j["s"])
    if k == "str":
        return Str(j["s"], j.get("bad"))
    if k == "var":
        p = j["path"]
        path = VarPath(_ref_py(p["doc"]), _ref_py(p["obj"]), bool(p["local"]), list(p["names"]), [_idc_py(c) for c in p["sub"]],
                       bool(p.get("forced")), bool(p.get("ownerNamed")), bool(p.get("plain")))
        if p.get("amb") is not None and deferred is not None:
            deferred.append((path, p["amb"]))
        comps = []
        for c in j["comps"]:
            if "name" in c:
                comps.append(ExprAttr(c["name"]))
            else:
                comps.append(ExprIndex(*(None if c[e] is None else node_from_js(c[e], deferred) for e in ("e1", "e2", "e3")), bool(c["range"])))
        return Var(path, comps)
    if k == "neg":
        return Neg(node_from_js(j["a"], deferred))
    if k == "pos":
        return Pos(node_from_js(j["a"], deferred))
    if k == "op":
        return Op(j["op"], node_from_js(j["l"], deferred), node_from_js(j["r"], deferred))
    if k == "fn":
        return Fn(j["f"], j["name"], [node_from_js(a, deferred) for a in j["args"]])
    if k == "cond":
        return Cond(node_from_js(j["c"], deferred), node_from_js(j["t"], deferred), node_from_js(j["f"], deferred))
    return Range(j["a"], j["b"])


def _recursion():
    return ExprError("maximum recursion depth exceeded", "RecursionError")


# ─── Parsing and printing ─────────────────────────────────────────────────────────────────────────

def parse(text, names=frozenset(), owner=None, resolve_ambiguity=None):
    """Parse an expression (without a leading "="), as Expression.y does. `names` are the owner's properties: a unit's or
    constant's name among them reads as the property. Raises what FreeCAD raises. `resolve_ambiguity(obj: Ref, prop, owner)
    -> VarPath` decides what `Name.prop` names (ObjectIdentifier::resolveAmbiguity); without it, expr.ts's rule."""
    j = _call("parse", text, sorted(names), owner, resolve_ambiguity is not None)
    deferred = []
    try:
        tree = node_from_js(j, deferred)
    except RecursionError:
        raise _recursion() from None
    for path, amb in deferred:
        got = resolve_ambiguity(Ref(amb["obj"]["name"], bool(amb["obj"]["str"])), amb["prop"], owner)
        extra = path.names[amb["n"]:]
        path.doc, path.obj, path.local = got.doc, got.obj, got.local
        path.names = list(got.names) + extra
        path.sub = list(got.sub) + path.sub
        path.forced, path.owner_named, path.plain = got.forced, got.owner_named, got.plain
    return tree


def _js(n, ids=None):
    try:
        return _dumps(node_to_js(n, ids))
    except RecursionError:
        raise _recursion() from None


def to_text(n):
    """Expression::toString."""
    return _call("toText", _js(n))


def parse_unit(text):
    """ExpressionParser::parseUnit: (dims, scaler), e.g. "cm" -> (Length, 10.0)."""
    r = _call("parseUnit", text)
    return tuple(r["dims"]), float(r["scaler"])


def is_token_a_unit(s):
    """ExpressionParser::isTokenAUnit."""
    return _call("isTokenAUnit", s)


def is_token_a_constant(s):
    """ExpressionParser::isTokenAConstant."""
    return _call("isTokenAConstant", s)


def py_str(v):
    """Python's str() of a value, as FreeCAD's Python prints it."""
    return _call("pyStr", _dumps(value_to_js(v)))


def user_string(q, schema=None, decimals=None, denominator=None):
    """UnitsSchema::translate: (text, factor, unit), e.g. ("12.50 mm", 1.0, "mm")."""
    text, factor, unit = _call("userString", _dumps({"value": _f(q.value), "dims": list(q.dims)}), schema, decimals, denominator)
    return text, factor, unit


def to_number(v, fmt, decimals):
    """QLocale::toString of a number in the Default, Fixed or Scientific format."""
    return _call("toNumber", _dumps(_f(v)), fmt, decimals)


# ─── Evaluation ──────────────────────────────────────────────────────────────────────────────────

class Env:
    """What an expression can name. vars: the owner's properties (a dict, or a mapping that answers `in` and [] by name).
    owner, doc: the names of the object that owns the expression and of its document. resolve(path) -> (value, rest_names): a
    name that is not the owner's (another object, another document, or two names of which the first is not a property).
    range_cells(range_node) -> [(addr, value, kind)] or None: a sheet's cells of a range in its order; None (or no hook) takes
    them from vars, row by row. resolve_ambiguity: passed to parse by evaluate_value."""

    def __init__(self, vars, owner=None, doc=None, resolve=None, range_cells=None, resolve_ambiguity=None):   # noqa: A002
        self.vars = vars
        self.owner = owner
        self.doc = doc
        self.resolve = resolve
        self.range_cells = range_cells
        self.resolve_ambiguity = resolve_ambiguity


def _error_entry(e):
    return {"error": e.message, "etype": getattr(e, "etype", "QuantityError"), "kind": e.kind}


def _env_js(n, env):
    """The env's JSON for tree n: the owner's properties it reads, and what resolve and range_cells answer for its names and
    ranges (asked where expr.ts would ask them: a name of another object, or two names of which the first is no property)."""
    ids, resolved, ranges = {}, {}, {}
    whole = isinstance(env.vars, dict)
    vars_js = {k: value_to_js(v) for k, v in env.vars.items()} if whole else {}

    def var(name):
        if whole or name in vars_js:
            return
        if name in env.vars:
            vars_js[name] = value_to_js(env.vars[name])
    owner, doc = env.owner or "", env.doc or ""
    for x in walk(n):
        t = type(x)
        if t is Var:
            p = x.path
            if p.names:
                var(p.names[0])
            if env.resolve is not None and ((p.doc is not None and p.doc.name != doc) or (p.obj is not None and p.obj.name != owner)
                                            or (len(p.names) >= 2 and p.names[0] not in env.vars)):
                i = ids[id(p)] = len(ids)
                try:
                    value, rest = env.resolve(p)
                    resolved[i] = {"value": value_to_js(value), "rest": list(rest)}
                except QuantityError as e:
                    resolved[i] = _error_entry(e)
        elif t is Range:
            got = None
            if env.range_cells is not None:
                i = ids[id(x)] = len(ids)
                try:
                    got = env.range_cells(x)
                    if got is not None:
                        ranges[i] = [{"addr": a, "value": value_to_js(v), **({"kind": k} if k is not None else {})} for a, v, k in got]
                except QuantityError as e:
                    ranges[i] = got = _error_entry(e)
            if got is None:
                try:
                    for a in range_cells(x):
                        var(a)
                except ExprError:
                    pass   # the engine says what is wrong with the range
    return ids, {"vars": vars_js, "owner": env.owner, "doc": env.doc, "resolved": resolved, "ranges": ranges}


def _value(j):
    try:
        return value_from_js(j)
    except RecursionError:
        raise _recursion() from None


def evaluate(n, env):
    """Evaluate a tree against the owner's properties (FreeCAD's getPyValue): a Python value."""
    ids, e = _env_js(n, env)
    return _value(_call("evaluate", _js(n, ids), _dumps(e)))


def evaluate_value(text, env):
    """Evaluate an expression (without its leading "=") to a Python value."""
    if env.resolve is None and env.range_cells is None and env.resolve_ambiguity is None and isinstance(env.vars, dict):
        e = {"vars": {k: value_to_js(v) for k, v in env.vars.items()}, "owner": env.owner, "doc": env.doc}
        return _value(_call("evaluateText", text, _dumps(e)))   # one call, and no tree too deep for Python to carry
    return evaluate(parse(text, frozenset(env.vars) if isinstance(env.vars, dict) else frozenset(), env.owner,
                          resolve_ambiguity=env.resolve_ambiguity), env)


# ─── Walking the tree (the ExpressionVisitors a spreadsheet uses) ─────────────────────────────────

_CELL = re.compile(r"(\$?)([A-Z]{1,2})(\$?)([0-9]+)")


def string_to_address(s):
    """(row, col), 1-based, of a cell address, or None."""
    m = _CELL.fullmatch(s)
    if not m:
        return None
    col = 0
    for ch in m.group(2):
        col = col * 26 + (ord(ch) - 64)
    row = int(m.group(4))
    return (row, col) if 1 <= row <= 16384 and 1 <= col <= 702 else None


def column_name(col):
    return (chr(64 + (col - 1) // 26) if col > 26 else "") + chr(65 + (col - 1) % 26)


def range_cells(n):
    """The addresses of Range n, row by row (expr.ts's order)."""
    c1, c2 = string_to_address(n.a), string_to_address(n.b)
    if not c1 or not c2:
        raise ExprError(f"Invalid cell range {n.a}:{n.b}\nin expression: {n.a}:{n.b}", "ExpressionError")
    return [f"{column_name(c)}{r}" for r in range(min(c1[0], c2[0]), max(c1[0], c2[0]) + 1)
            for c in range(min(c1[1], c2[1]), max(c1[1], c2[1]) + 1)]


def walk(n):
    """Every node of the tree, the root first: the operands, the arguments, the expressions of a name's indexers."""
    stack = [n]
    while stack:
        x = stack.pop()
        yield x
        t = type(x)
        kids = []
        if t is Var:
            for c in x.comps:
                if type(c) is ExprIndex:
                    kids += [e for e in (c.e1, c.e2, c.e3) if e is not None]
        elif t is Neg or t is Pos:
            kids = [x.a]
        elif t is Op:
            kids = [x.l, x.r]
        elif t is Fn:
            kids = list(x.args)
        elif t is Cond:
            kids = [x.c, x.t, x.f]
        stack.extend(reversed(kids))


def identifiers(n):
    """Every VarPath the tree reads (Expression::getIdentifiers), in order; a Range gives one VarPath per cell (or its two ends,
    when they are not cell addresses: an alias)."""
    out = []
    for x in walk(n):
        if type(x) is Var:
            out.append(x.path)
        elif type(x) is Range:
            try:
                out.extend(VarPath(names=[a]) for a in range_cells(x))
            except ExprError:
                out.extend((VarPath(names=[x.a]), VarPath(names=[x.b])))
    return out


def copy(n):
    """Expression::copy."""
    return _copy.deepcopy(n)
