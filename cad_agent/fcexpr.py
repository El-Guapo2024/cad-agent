# SPDX-License-Identifier: LGPL-2.1-or-later
# Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
# LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
#   src/App/Expression.cpp: 2015 Eivind Kvedalen
#   src/App/Expression.l: 2010 Jürgen Riegel; 2015 Eivind Kvedalen
#   src/App/Expression.y: 2010 Jürgen Riegel; 2015 Eivind Kvedalen
#   src/App/ObjectIdentifier.cpp: 2015 Eivind Kvedalen
#   src/Base/Tools.h: 2009 Werner Mayer
#   src/Base/Vector3D.cpp: 2005 Imetric 3D GmbH
#   No copyright line in the file: src/App/QuantityInput.cpp
"""FreeCAD's expression language for the server: a port of ui/src/expr.ts (App/Expression.l, Expression.y, Expression.cpp at
FreeCAD main 3160daf1e2b6), so that Python evaluates spreadsheet cells and expressions bound to parameters exactly as the
browser does. The lexer, the grammar's LALR tables (fcexpr_data.json, from ui/src/expr-grammar.ts), the expression classes
(the Node classes below) with their toString, and their evaluation, which like FreeCAD's runs on Python's values and rules
(fcexpr_py.py). ui/scripts/exprdiff_py.py holds it to the real FreeCAD's answers on some 75,000 expressions.

    parse(text, names, owner)        -> a tree (Num, Const, UnitNode, Str, Var, Neg, Pos, Op, Fn, Cond, Range)
    to_text(node)                    -> Expression::toString
    evaluate(node, Env(vars, ...))   -> a Python value (int, float, bool, str, None, complex, list, tuple, Quantity, Vector, Other)
    evaluate_value(text, env)        -> parse and evaluate
    identifiers(node)                -> every VarPath the tree reads (ranges expanded to their cells)

The owner's properties take the place of the object's; Env.resolve, Env.range_cells and the resolve_ambiguity hook of parse let a
caller (a FreeCAD document, a spreadsheet) supply other objects' properties, cells, and the meaning of `Name.prop`."""
import math
import re
import unicodedata
from dataclasses import dataclass, field, replace
from typing import Optional, Union

from . import fcexpr_py as P
from .fcexpr_py import QUIRKS, ExprError, Other, Vector, py_repr, py_str
from .fcexpr_quantity import (DATA, EPSILON, UNITS, ZERO, Quantity, QuantityError, format_fixed, parse_quantity, to_number,
                              type_string, unit_string, user_string)

__all__ = ["ExprError", "QuantityError", "Quantity", "Vector", "Other", "QUIRKS", "MISSING",
           "Num", "Const", "UnitNode", "Str", "Var", "Neg", "Pos", "Op", "Fn", "Cond", "Range", "Node",
           "Ref", "VarPath", "IdAttr", "IdIndex", "IdKey", "IdRange", "ExprAttr", "ExprIndex",
           "parse", "parse_error", "parse_unit", "is_token_a_unit", "is_token_a_constant", "is_token_an_identifier", "to_text",
           "Env", "evaluate", "evaluate_value", "evaluate_quantity", "eval_node", "as_quantity", "result_text", "has_additive",
           "rewrite_ownerless", "apply_default_unit", "identifiers", "range_cells", "string_to_address", "column_name",
           "parse_quantity", "user_string", "unit_string", "type_string", "to_number", "format_fixed", "py_repr", "py_str",
           "default_resolve_ambiguity"]

MISSING = object()   # what Env.cell gives for a cell that is not there


# ─── The tree (NumberExpression, UnitExpression, OperatorExpression, FunctionExpression ...) ─────────────────────

@dataclass
class Ref:
    """A name as the grammar reads it (a document or an object): `str` when it was written as <<text>>."""
    name: str
    str: bool = False


@dataclass
class IdAttr:
    """ObjectIdentifier's components after the property: an attribute ..."""
    name: str


@dataclass
class IdIndex:
    """... a constant index ..."""
    i: int


@dataclass
class IdKey:
    """... a constant key ..."""
    key: str


@dataclass
class IdRange:
    """... or a constant range [b:e:s] (e None: open)."""
    b: int
    e: Optional[int]
    s: int = 1


IdComp = Union[IdAttr, IdIndex, IdKey, IdRange]


@dataclass
class VarPath:
    """ObjectIdentifier. doc and obj: what the text names (`Doc#Obj.prop`, `Obj.<<sub>>.prop`), None when it leaves them to the
    owner. local: a leading '.' (the owner's own property). names: the property, then the attributes the grammar gave as
    `.name`. sub: the components the identifier holds (attributes after the property, constant indices and ranges)."""
    doc: Optional[Ref] = None
    obj: Optional[Ref] = None
    local: bool = False
    names: list = field(default_factory=list)
    sub: list = field(default_factory=list)
    # set by a document's resolve_ambiguity hook (the spreadsheet's): `forced`, the object (and document) are written
    # out, as ObjectIdentifier::toString writes a documentObjectName that was set by force; `owner_named`, the text named
    # the owner, which a rename then writes out (VariableExpression::_renameObjectIdentifier)
    forced: bool = False
    owner_named: bool = False
    # `plain`: an `Obj.prop` whose Obj the document does not have, so the owner's property Obj (written as it was typed)
    plain: bool = False


@dataclass
class ExprAttr:
    """Expression::Component `.name`, for what the identifier could not hold."""
    name: str


@dataclass
class ExprIndex:
    """Expression::Component a[e1] or a[e1:e2:e3] (range: a ':' was written)."""
    e1: Optional["Node"] = None
    e2: Optional["Node"] = None
    e3: Optional["Node"] = None
    range: bool = False


ExprComp = Union[ExprAttr, ExprIndex]


@dataclass
class Num:
    v: float


@dataclass
class Const:
    name: str   # pi, e, None, True, False
    v: float


@dataclass
class UnitNode:
    q: Quantity
    s: str


@dataclass
class Str:
    s: str
    bad: Optional[str] = None   # what Python says when the text is not UTF-8


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
    op: str   # + - * / % ^ == != < > <= >= unit
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


def parse_error(text):
    """The error ParserExpression throws for a text it cannot read."""
    return ExprError(f"Failed to parse expression '{text}'", "ParserError", "syntax")


# ─── The lexer (Expression.l) ──────────────────────────────────────────────────────────────────────

TERMINALS = DATA["terminals"]
NONTERMINALS = DATA["nonterminals"]
RULES = [tuple(r) for r in DATA["rules"]]
_TERM = {t: i for i, t in enumerate(TERMINALS)}


def _T(name):
    return _TERM.get(name, -1)


_UNIT_TOKENS = sorted(UNITS, key=len, reverse=True)
_RE_UNIT = re.compile("|".join(re.escape(u) for u in _UNIT_TOKENS))
_RE_WS = re.compile(r"[ \t]+")
_RE_STRING = re.compile(r"<<(?:\\[\s\S]|[^\\>\n])*>>")
_RE_CHAR = re.compile(r"[%+()=/*^,.{}\[\]:;@?#]")
_RE_N1 = re.compile(r"[0-9]*\.[0-9]+(?:[eE][-+]?[0-9]+)?")
_RE_N2 = re.compile(r"[0-9]*,[0-9]+(?:[eE][-+]?[0-9]+)?")
_RE_N3 = re.compile(r"[0-9]+[eE][-+]?[0-9]+")
_RE_N4 = re.compile(r"[0-9]+")
_RE_CONST = re.compile(r"None|True|true|False|false|pi|e")
_RE_CELLS = (re.compile(r"\$[A-Za-z]+\$[0-9]+"), re.compile(r"[A-Za-z]{1,2}\$[0-9]+"), re.compile(r"\$[A-Za-z]{1,2}[0-9]+"))
_SIMPLE_OPS = ("==", "!=", ">=", "<=", ">", "<")
_OP_TOKEN = {"==": "EQ", "!=": "NEQ", ">": "GT", "<": "LT", ">=": "GTE", "<=": "LTE"}

#: The function names Expression.y's lexer registers (initParser).
FUNCTIONS = frozenset("""abs acos asin atan atan2 cath cbrt ceil cos cosh exp floor hypot log log10 mod pow round sin sinh sqrt tan
tanh trunc vangle vcross vdot vlinedist vlinesegdist vlineproj vnormalize vplanedist vplaneproj vscale vscalex vscaley vscalez
minvert mrotate mrotatex mrotatey mrotatez mscale mtranslate create list matrix placement rotation rotationx rotationy rotationz
str parsequant translationm tuple vector address hiddenref href not average count max min stddev sum and or""".split())

_CONSTANTS = {"pi": ("pi", math.pi), "e": ("e", math.e), "None": ("None", 0.0), "True": ("True", 1.0), "true": ("True", 1.0),
              "False": ("False", 0.0), "false": ("False", 0.0)}

_CAT = {}


def _cat(c):
    k = _CAT.get(c)
    if k is None:
        k = _CAT[c] = unicodedata.category(c)[0]
    return k


def _scan_name(text, i, func):
    """\\p{L}\\p{M}* or '_' first (a function: a letter), then letters (each with its marks), digits, '_' and (not in a function)
    '@'. The end, or i when nothing matches."""
    n = len(text)
    if i >= n:
        return i
    c = text[i]
    if c != "_" and _cat(c) == "L":
        i += 1
        while i < n and _cat(text[i]) == "M":
            i += 1
    elif c == "_" and not func:
        i += 1
    else:
        return i
    while i < n:
        c = text[i]
        k = _cat(c)
        if k == "L" and c != "_":
            i += 1
            while i < n and _cat(text[i]) == "M":
                i += 1
        elif k == "N" or c == "_" or (c == "@" and not func):
            i += 1
        else:
            break
    return i


def _num_change(text, dez, grp):
    """num_change: the digits of a number with `grp` left out and `dez` as the point; 40 characters or more is 0."""
    t = []
    n = 0
    for c in text:
        if c == grp:
            continue
        t.append("." if c == dez and dez != "." else c)
        n += 1
        if n > 39:
            return 0.0
    s = "".join(t)
    v = float(s)
    if v == 0 and re.search("[1-9]", re.split("[eE]", s)[0]):
        raise ExprError("Number underflow.", "ArithmeticError")
    if math.isinf(v):
        raise ExprError("Number overflow.", "OverflowError")
    return v


def _unquote(lexeme):
    """unquote: the text of a <<string>>, escapes resolved, byte by byte: (text, what Python says if it is not UTF-8)."""
    raw = lexeme.encode("utf-8", "surrogatepass")[2:-2]
    out = bytearray()
    escaped = False
    for c in raw:
        if escaped:
            if c == 0x74:
                out.append(9)
            elif c == 0x6E:
                out.append(10)
            elif c == 0x72:
                out.append(13)
            elif c in (0x5C, 0x27, 0x22):
                out.append(c)
            escaped = False
        elif c == 0x5C:
            escaped = True
        else:
            out.append(c)
    try:
        return bytes(out).decode("utf-8"), None
    except UnicodeDecodeError:
        pass
    at = 0
    while at < len(out):
        c = out[at]
        ln = 1 if c < 0x80 else 2 if 0xC2 <= c < 0xE0 else 3 if 0xE0 <= c < 0xF0 else 4 if 0xF0 <= c < 0xF5 else 0
        if ln == 0:
            break
        if at + ln > len(out):
            return "", f"'utf-8' codec can't decode byte {hex(c)} in position {at}: unexpected end of data"
        if any((x & 0xC0) != 0x80 for x in out[at + 1:at + ln]):
            return "", f"'utf-8' codec can't decode byte {hex(c)} in position {at}: invalid continuation byte"
        at += ln
    return "", f"'utf-8' codec can't decode byte {hex(out[at] if at < len(out) else 0)} in position {at}: invalid start byte"


class _Lexer:
    def __init__(self, text, names):
        self.text = text
        self.names = names
        self.i = 0

    def next(self):
        """The next token (number, value): the longest match first and the earlier rule on a tie; a character no rule takes is
        skipped (flex's default rule)."""
        text = self.text
        while True:
            i = self.i
            if i >= len(text):
                return 0, None
            best, kind = 0, ""

            def consider(k, end):
                nonlocal best, kind
                if end is not None and end - i > best:
                    best, kind = end - i, k

            def m(rx):
                r = rx.match(text, i)
                return r.end() if r else None
            c0 = text[i]
            consider("ws", m(_RE_WS))
            if c0 == "\n":
                consider("nl", i + 1)
            if c0 == "<":
                consider("str", m(_RE_STRING))
            consider("char", m(_RE_CHAR))
            for op in _SIMPLE_OPS:
                if text.startswith(op, i):
                    consider("op", i + len(op))
            if c0 == "-" or c0 == "−":
                consider("minus", i + 1)
            consider("unit", m(_RE_UNIT))
            if c0 in "0123456789.,":
                consider("n1", m(_RE_N1))
                consider("n2", m(_RE_N2))
                consider("n3", m(_RE_N3))
                consider("n4", m(_RE_N4))
            consider("const", m(_RE_CONST))
            if c0 == "$" or c0.isascii() and c0.isalpha():
                for rx in _RE_CELLS:
                    consider("cell", m(rx))
            j = _scan_name(text, i, True)
            if j > i:
                k = j
                while k < len(text) and text[k] in "\x10\t":
                    k += 1
                if k < len(text) and text[k] == "(":
                    consider("func", k + 1)
            j = _scan_name(text, i, False)
            if j > i:
                consider("id", j)
            if best == 0:   # flex's default rule: copy the character to the output and go on
                self.i += 1
                continue
            lexeme = text[i:i + best]
            self.i += best
            if kind in ("ws", "nl"):
                continue
            if kind == "str":
                return _T("STRING"), _unquote(lexeme)
            if kind == "char":
                return _T(f"'{lexeme}'"), lexeme
            if kind == "op":
                return _T(_OP_TOKEN[lexeme]), None
            if kind == "minus":
                return _T("MINUSSIGN"), None
            if kind == "unit":
                if lexeme in self.names:
                    return _T("IDENTIFIER"), lexeme
                value, dims = UNITS[lexeme]
                return _T("USUNIT" if lexeme in ('"', "'") else "UNIT"), (Quantity(value, dims), lexeme)
            if kind in ("n1", "n2", "n3"):
                if kind == "n2":
                    v = _num_change(lexeme, ",", ".")
                else:
                    v = _num_change(lexeme, "." if kind == "n1" else ",", "," if kind == "n1" else ".")
                return _T("ONE" if v == 1 else "NUM"), v
            if kind == "n4":
                v = int(lexeme)
                if v >= 9223372036854775807:
                    raise ExprError("Integer overflow", "OverflowError")
                return (_T("ONE"), 1.0) if v == 1 else (_T("INTEGER"), float(v))
            if kind == "const":
                if lexeme in self.names:
                    return _T("IDENTIFIER"), lexeme
                return _T("CONSTANT"), _CONSTANTS[lexeme]
            if kind == "cell":
                return _T("CELLADDRESS"), lexeme
            if kind == "func":
                name = lexeme[:-1].rstrip(" \t\n\v\f\r")
                return _T("FUNC"), (name, name in FUNCTIONS)
            return _T("IDENTIFIER"), lexeme


# ─── The expression classes' checks and printing ─────────────────────────────────────────────────

def _arity():
    one = (lambda n: n == 1, "exactly one required.")
    two = (lambda n: n == 2, "exactly two required.")
    two_three = (lambda n: 2 <= n <= 3, "exactly two, or three required.")
    three = (lambda n: n == 3, "exactly three required.")
    at_least_one = (lambda n: n >= 1, "at least one required.")
    out = {}
    for f in ("abs acos asin atan cbrt ceil cos cosh exp floor hiddenref href log log10 minvert rotationx rotationy rotationz round "
              "sin sinh sqrt str parsequant tan tanh trunc vnormalize not").split():
        out[f] = one
    out["placement"] = (lambda n: n <= 3, "exactly one, two, or three required.")
    out["translationm"] = (lambda n: n in (1, 3), "exactly one or three required.")
    for f in "atan2 mod mrotatex mrotatey mrotatez pow vangle vcross vdot vscalex vscaley vscalez".split():
        out[f] = two
    for f in ("address", "cath", "hypot", "rotation"):
        out[f] = two_three
    for f in ("mtranslate", "mscale"):
        out[f] = (lambda n: n in (2, 4), "exactly two or four required.")
    out["mrotate"] = (lambda n: 2 <= n <= 4, "exactly two, three, or four required.")
    for f in ("vector", "vlinedist", "vlinesegdist", "vlineproj", "vplanedist", "vplaneproj"):
        out[f] = three
    out["vscale"] = (lambda n: n == 4, "exactly four required.")
    out["matrix"] = (lambda n: n <= 16, "exactly 16 or less required.")
    for f in ("average", "count", "create", "max", "min", "stddev", "sum", "and", "or"):
        out[f] = at_least_one
    out["list"] = None
    out["tuple"] = None
    return out


ARITY = _arity()
_CMP_OPS = ("==", "!=", "<", ">", "<=", ">=")


def priority(n):
    """Expression::priority()."""
    t = type(n)
    if t is Op:
        o = n.op
        if o in _CMP_OPS:
            return 1
        if o in ("+", "-"):
            return 3
        if o in ("*", "/", "%"):
            return 4
        if o == "^":
            return 5
        return 6
    if t is Neg or t is Pos:
        return 6
    if t is Cond:
        return 2
    return 20


def _number_text(v):
    return to_number(v, "Default", 15)


def quote(s):
    """App::quote: <<text>> with the characters the lexer reads as escapes written as escapes."""
    return "<<" + s.replace("\\", "\\\\").replace("\n", "\\n").replace("\t", "\\t").replace("\r", "\\r").replace('"', '\\"') \
        .replace("'", "\\'") + ">>"


def _id_comp_text(c):
    t = type(c)
    if t is IdAttr:
        return "." + c.name
    if t is IdIndex:
        return f"[{c.i}]"
    if t is IdKey:
        return f"[{quote(c.key)}]"
    return f"[{c.b}:{'' if c.e is None else c.e}{':' + str(c.s) if c.s != 1 else ''}]"


def path_text(p):
    """ObjectIdentifier::toString as expr.ts has it: the property, a '.' before it if it is the owner's own and attributes follow."""
    props = "".join(nm if i == 0 else "." + nm for i, nm in enumerate(p.names))
    if p.plain:
        return props + "".join(_id_comp_text(c) for c in p.sub)
    if p.forced and p.obj is not None:
        head = (_ref_text(p.doc) + "#" if p.doc is not None else "") + _ref_text(p.obj) + "."
        return head + props + "".join(_id_comp_text(c) for c in p.sub)
    return ("." if p.local or len(p.names) > 1 else "") + props + "".join(_id_comp_text(c) for c in p.sub)


def to_text(n):
    """Expression::toString."""
    t = type(n)
    if t is Num:
        return _number_text(n.v)
    if t is Const:
        return n.name
    if t is UnitNode:
        return n.s
    if t is Str:
        return quote(n.s)
    if t is Range:
        return f"{n.a}:{n.b}"
    if t is Var:
        s = path_text(n.path)
        for c in n.comps:
            if type(c) is ExprAttr:
                s += "." + c.name
            else:
                s += ("[" + (to_text(c.e1) if c.e1 is not None else "") + (":" if c.e2 is not None or c.range else "")
                      + (to_text(c.e2) if c.e2 is not None else "") + (":" + to_text(c.e3) if c.e3 is not None else "") + "]")
        return s
    if t is Neg or t is Pos:
        parens = priority(n.a) < 6
        inner = to_text(n.a)
        return ("-" if t is Neg else "+") + (f"({inner})" if parens else inner)
    if t is Op:
        pn = priority(n)
        left = priority(n.l) < pn or (n.op == "unit" and type(n.l) not in (Num, Const))
        s = f"({to_text(n.l)})" if left else to_text(n.l)
        s += " " if n.op == "unit" else f" {n.op} "
        rop = n.r.op if type(n.r) is Op else None
        pr = priority(n.r)
        right = False
        if pr < pn:
            right = True
        elif rop == n.op:
            right = n.op not in ("+", "*")   # not right-associative, or not commutative
        elif pr == pn:
            right = n.op not in ("+", "*") or rop == "%"
        return s + (f"({to_text(n.r)})" if right else to_text(n.r))
    if t is Fn:
        return f"{n.name}({'; '.join(to_text(a) for a in n.args)})"
    if t is Cond:
        def wrap(x):
            return f"({to_text(x)})" if priority(x) <= 2 else to_text(x)
        return f"{to_text(n.c)} ? {wrap(n.t)} : {wrap(n.f)}"
    raise TypeError(f"not an expression node: {n!r}")


def _in_expr(msg, n):
    return f"{msg}\nin expression: {to_text(n)}"


# ─── The parser (Expression.y's actions on the tables) ───────────────────────────────────────────────────────

def _essentially_equal(a, b):
    return abs(a - b) <= min(abs(a), abs(b)) * EPSILON


def _num_like(n):
    return type(n) in (Num, Const)


def _essentially_integer(v):
    return int(v) if math.isfinite(v) and v == math.floor(v) and abs(v) <= 9223372036854775807 else None


def _add_component(n, c):
    """VariableExpression::addComponent: a constant index or range is folded into the identifier, the rest stays an expression."""
    if not n.comps:
        if type(c) is ExprAttr:
            n.path.sub.append(IdAttr(c.name))
            return
        while True:   # a block to break out of
            if c.e1 is None and c.e2 is None:
                n.path.sub.append(IdRange(0, None, 1))   # Bison's `createComponent(0,0,e)` drops the step too
                return
            l1 = 0
            if c.e3 is not None and (not _num_like(c.e3) or not _essentially_equal(c.e3.v, 1)):
                break
            if c.e1 is not None:
                if not _num_like(c.e1):
                    if c.e2 is not None or c.e3 is not None or type(c.e1) is not Str:
                        break
                    n.path.sub.append(IdKey(c.e1.s))
                    return
                i1 = _essentially_integer(c.e1.v)
                if i1 is None:
                    break
                l1 = i1
                if not c.range:
                    n.path.sub.append(IdIndex(l1))
                    return
                if c.e2 is None:
                    n.path.sub.append(IdRange(l1, 0, 1))
                    return
            if _num_like(c.e2):
                i2 = _essentially_integer(c.e2.v)
                if i2 is not None:
                    n.path.sub.append(IdRange(l1, i2, 1))
                    return
            break
    n.comps.append(c)


def default_resolve_ambiguity(obj, prop, owner):
    """ObjectIdentifier::resolveAmbiguity as expr.ts has it, for `Name.prop`: the owner's name is dropped, any other name is a
    property of the owner (then an attribute)."""
    return VarPath(names=[prop] if obj.name == owner else [obj.name, prop])


class _Ctx:
    __slots__ = ("result", "value", "unit", "owner", "resolve_ambiguity")

    def __init__(self, owner, resolve_ambiguity):
        self.result = None
        self.value = False
        self.unit = False
        self.owner = owner
        self.resolve_ambiguity = resolve_ambiguity or default_resolve_ambiguity


def _make_function(tok, args):
    """FunctionExpression's constructor: the checks on the name and the number of arguments."""
    name, known = tok
    if not known:
        raise ExprError("Unknown function", "ParserError", "syntax")
    node = Fn(name, name, args)
    rule = ARITY.get(name)
    if rule and not rule[0](len(args)):
        raise ExprError(_in_expr(f"Invalid number of arguments: {rule[1]}", node), "ExpressionError")
    return node


def _set(c, attr, v):
    c.result = v
    setattr(c, attr, True)


def _str_node(v):
    return Str(v[0], v[1])


_ACTIONS = {
    "input: exp": lambda v, c: _set(c, "value", v[0]),
    "input: unit_exp": lambda v, c: _set(c, "unit", v[0]),
    "unit_num: num unit_exp %prec NUM_AND_UNIT": lambda v, c: Op("unit", v[0], v[1]),
    "unit_num: '(' exp ')' unit_exp %prec NUM_AND_UNIT": lambda v, c: Op("unit", v[1], v[3]),
    "unit_num: num us_building_unit num us_building_unit %prec NUM_AND_UNIT": lambda v, c: Op("+", Op("unit", v[0], v[1]), Op("unit", v[2], v[3])),
    "exp: num": lambda v, c: v[0],
    "exp: unit_num": lambda v, c: v[0],
    "exp: STRING": lambda v, c: _str_node(v[0]),
    "exp: identifier": lambda v, c: Var(v[0]),
    "exp: MINUSSIGN exp %prec NEG": lambda v, c: Neg(v[1]),
    "exp: '+' exp %prec POS": lambda v, c: Pos(v[1]),
    "exp: exp '+' exp": lambda v, c: Op("+", v[0], v[2]),
    "exp: exp MINUSSIGN exp": lambda v, c: Op("-", v[0], v[2]),
    "exp: exp '*' exp": lambda v, c: Op("*", v[0], v[2]),
    "exp: exp '/' exp": lambda v, c: Op("/", v[0], v[2]),
    "exp: exp '%' exp": lambda v, c: Op("%", v[0], v[2]),
    "exp: exp '/' unit_exp": lambda v, c: Op("/", v[0], v[2]),
    "exp: exp '^' exp": lambda v, c: Op("^", v[0], v[2]),
    "exp: exp EQ exp": lambda v, c: Op("==", v[0], v[2]),
    "exp: exp NEQ exp": lambda v, c: Op("!=", v[0], v[2]),
    "exp: exp LT exp": lambda v, c: Op("<", v[0], v[2]),
    "exp: exp GT exp": lambda v, c: Op(">", v[0], v[2]),
    "exp: exp GTE exp": lambda v, c: Op(">=", v[0], v[2]),
    "exp: exp LTE exp": lambda v, c: Op("<=", v[0], v[2]),
    "exp: indexable": lambda v, c: v[0],
    "exp: FUNC args ')'": lambda v, c: _make_function(v[0], v[1]),
    "exp: exp '?' exp ':' exp": lambda v, c: Cond(v[0], v[2], v[4]),
    "exp: '(' exp ')'": lambda v, c: v[1],
    "num: ONE": lambda v, c: Num(v[0]),
    "num: NUM": lambda v, c: Num(v[0]),
    "num: INTEGER": lambda v, c: Num(v[0]),
    "num: CONSTANT": lambda v, c: Const(v[0][0], v[0][1]),
    "args: exp": lambda v, c: [v[0]],
    "args: range": lambda v, c: [v[0]],
    "args: args ',' exp": lambda v, c: v[0] + [v[2]],
    "args: args ';' exp": lambda v, c: v[0] + [v[2]],
    "args: args ',' range": lambda v, c: v[0] + [v[2]],
    "args: args ';' range": lambda v, c: v[0] + [v[2]],
    "range: id_or_cell ':' id_or_cell": lambda v, c: Range(v[0], v[2]),
    "us_building_unit: USUNIT": lambda v, c: UnitNode(v[0][0], v[0][1]),
    "other_unit: UNIT": lambda v, c: UnitNode(v[0][0], v[0][1]),
    "unit_exp: other_unit": lambda v, c: v[0],
    "unit_exp: us_building_unit": lambda v, c: v[0],
    "unit_exp: unit_exp '/' unit_exp": lambda v, c: Op("/", v[0], v[2]),
    "unit_exp: unit_exp '*' unit_exp": lambda v, c: Op("*", v[0], v[2]),
    "unit_exp: unit_exp '^' integer": lambda v, c: Op("^", v[0], Num(v[2])),
    "unit_exp: unit_exp '^' MINUSSIGN integer": lambda v, c: Op("^", v[0], Neg(Num(v[3]))),
    "unit_exp: '(' unit_exp ')'": lambda v, c: v[1],
    "integer: INTEGER": lambda v, c: v[0],
    "integer: ONE": lambda v, c: v[0],
    "id_or_cell: IDENTIFIER": lambda v, c: v[0],
    "id_or_cell: CELLADDRESS": lambda v, c: v[0],
    "identifier: id_or_cell": lambda v, c: VarPath(names=[v[0]]),
    "identifier: iden": lambda v, c: v[0],
    "iden: '.' STRING '.' id_or_cell": lambda v, c: VarPath(local=True, names=[v[3]]),
    "iden: '.' id_or_cell": lambda v, c: VarPath(local=True, names=[v[1]]),
    "iden: object '.' STRING '.' id_or_cell": lambda v, c: VarPath(obj=v[0], names=[v[4]]),
    # ObjectIdentifier::resolveAmbiguity: the hook decides (by default: the owner's name dropped, else a property of the owner)
    "iden: object '.' id_or_cell": lambda v, c: c.resolve_ambiguity(v[0], v[2], c.owner),
    "iden: document '#' object '.' id_or_cell": lambda v, c: VarPath(doc=v[0], obj=v[2], names=[v[4]]),
    "iden: document '#' object '.' STRING '.' id_or_cell": lambda v, c: VarPath(doc=v[0], obj=v[2], names=[v[6]]),
    "iden: iden '.' IDENTIFIER": lambda v, c: replace(v[0], names=v[0].names + [v[2]], sub=list(v[0].sub)),
    "indexer: '[' exp ']'": lambda v, c: ExprIndex(v[1], None, None, False),
    "indexer: '[' exp ':' ']'": lambda v, c: ExprIndex(v[1], None, None, True),
    "indexer: '[' ':' exp ']'": lambda v, c: ExprIndex(None, v[2], None, True),
    "indexer: '[' ':' ':' exp ']'": lambda v, c: ExprIndex(None, None, v[3], True),
    "indexer: '[' exp ':' exp ']'": lambda v, c: ExprIndex(v[1], v[3], None, True),
    "indexer: '[' exp ':' ':' exp ']'": lambda v, c: ExprIndex(v[1], None, v[4], True),
    "indexer: '[' ':' exp ':' exp ']'": lambda v, c: ExprIndex(None, v[2], v[4], True),
    "indexer: '[' exp ':' exp ':' exp ']'": lambda v, c: ExprIndex(v[1], v[3], v[5], True),
    "indexable: identifier indexer": lambda v, c: _indexed(Var(v[0]), v[1]),
    "indexable: indexable indexer": lambda v, c: _indexed(v[0], v[1]),
    "indexable: indexable '.' IDENTIFIER": lambda v, c: _indexed(v[0], ExprAttr(v[2])),
    "document: STRING": lambda v, c: Ref(v[0][0], True),
    "document: IDENTIFIER": lambda v, c: Ref(v[0], False),
    "object: STRING": lambda v, c: Ref(v[0][0], True),
    "object: id_or_cell": lambda v, c: Ref(v[0], False),
}


def _indexed(n, c):
    _add_component(n, c)
    return n


def _rule_actions():
    out = []
    for _, _, text in RULES:
        a = _ACTIONS.get(text)
        if a is None and text != "$accept: input $end":
            raise RuntimeError(f"fcexpr.py has no action for the grammar rule {text!r}: regenerate fcexpr_data.json and update _ACTIONS")
        out.append(a)
    return out


_RULE_ACTIONS = _rule_actions()
# per state: (shift {token: state}, reduce {token: rule}, default rule or -1, goto {nonterminal: state}, whether it reads a token)
_STATES = [(dict(zip(s[0][::2], s[0][1::2])), dict(zip(s[1][::2], s[1][1::2])), s[2], dict(zip(s[3][::2], s[3][1::2])), bool(s[4]))
           for s in DATA["states"]]


def _hook(ctx_hooks, name):
    if ctx_hooks is None:
        return None
    if isinstance(ctx_hooks, dict):
        return ctx_hooks.get(name)
    return getattr(ctx_hooks, name, None)


def _run_parser(text, names, owner, resolve_ambiguity):
    lexer = _Lexer(text, names)
    ctx = _Ctx(owner, resolve_ambiguity)
    states = [0]
    values = [None]
    tok = None
    while True:
        shifts, reds, default, _, needs = _STATES[states[-1]]
        shift = reduce = None
        if needs:
            if tok is None:
                tok = lexer.next()
            shift = shifts.get(tok[0])
            if shift is None:
                reduce = reds.get(tok[0])
        if shift is None and reduce is None:
            if default < 0:
                raise parse_error(text)
            reduce = default
        if shift is not None:
            if shift < 0:   # $end shifted: the input is complete
                break
            states.append(shift)
            values.append(tok[1])
            tok = None
            continue
        lhs, ln, _ = RULES[reduce]
        if ln:
            args = values[-ln:]
            del values[-ln:]
            del states[-ln:]
        else:
            args = []
        values.append(_RULE_ACTIONS[reduce](args, ctx))
        nxt = _STATES[states[-1]][3].get(lhs)
        if nxt is None:
            raise parse_error(text)
        states.append(nxt)
    return ctx


def _recursion():
    return ExprError("maximum recursion depth exceeded", "RecursionError")


def parse(text, names=frozenset(), owner=None, ctx_hooks=None, resolve_ambiguity=None):
    """Parse an expression (without a leading "="), as Expression.y does, building FreeCAD's expression classes. `names` are the
    owner's properties: a unit's or constant's name among them reads as the property. Raises what FreeCAD raises: ParserError
    for text that is not an expression ("Failed to parse expression '...'"), and the lexer's and constructors' own errors.
    `owner` is the name of the object the expression belongs to. `resolve_ambiguity(obj: Ref, prop: str, owner) -> VarPath`
    (or ctx_hooks['resolve_ambiguity']) decides what `Name.prop` names (ObjectIdentifier::resolveAmbiguity)."""
    ra = resolve_ambiguity or _hook(ctx_hooks, "resolve_ambiguity")
    try:
        ctx = _run_parser(text, names, owner, ra)
    except RecursionError:
        raise _recursion() from None
    if ctx.result is None:
        raise ExprError(f"Unknown error in expression '{text}'", "ParserError", "syntax")
    if not ctx.value:
        raise ExprError("Expression can not evaluate to a value.", "FreeCADError", "syntax")
    return ctx.result


def parse_unit(text, owner=None):
    """ExpressionParser::parseUnit: a unit expression (or 1/unit), simplified: (dims, scaler), e.g. "cm" -> (Length, 10.0)."""
    try:
        ctx = _run_parser(text, frozenset(), owner, None)
    except ExprError as e:
        if e.kind == "syntax" and e.message == f"Failed to parse expression '{text}'":
            raise ExprError("Failed to parse expression.", "ParserError", "syntax") from None
        raise
    if ctx.result is None:
        raise ExprError("Unknown error in expression", "ParserError", "syntax")
    unit = ctx.unit
    r = ctx.result
    if not unit and type(r) is Op and r.op == "/" and type(r.l) in (Num, Const) and type(r.r) is UnitNode and _essentially_equal(r.l.v, 1.0):
        unit = True
    if not unit:
        raise ExprError("Expression is not a unit.", "ExpressionError")
    q = as_quantity(evaluate(r, Env({})))
    return q.dims, q.value


def _first_tokens(s):
    lx = _Lexer(s, frozenset())
    return lx.next()[0], lx.next()[0]


def is_token_a_unit(s):
    """ExpressionParser::isTokenAUnit: the text is one UNIT token (a US building unit, " or ', is not)."""
    tok, status = _first_tokens(s)
    return status == 0 and tok == _T("UNIT")


def is_token_a_constant(s):
    """ExpressionParser::isTokenAConstant."""
    tok, status = _first_tokens(s)
    return status == 0 and tok == _T("CONSTANT")


def is_token_an_identifier(s):
    """ExpressionParser::isTokenAnIndentifier: one IDENTIFIER or CELLADDRESS token."""
    tok, status = _first_tokens(s)
    return status == 0 and tok in (_T("IDENTIFIER"), _T("CELLADDRESS"))


# ─── Evaluation (Expression.cpp's _getPyValue) ────────────────────────────────────────────────────

class Env:
    """What an expression can name. vars: the owner's properties (Python values or Quantity; a dimensionless Quantity reads as a
    float, as PropertyFloat gives). owner, doc: the name of the object that owns the expression and of its document.
    resolve(path) -> (value, rest_names): a name that is not the owner's (another object, another document, or two or more names
    of which the first is not a property); without it, expr.ts's errors. range_cells(range_node) -> [(addr, value, kind)] or
    None: the cells of a range in FreeCAD's order, `kind` the cell property's type ('quantity', 'float', 'int', or another);
    None (or no hook) takes them from vars, row by row. resolve_ambiguity: passed to parse by evaluate_value."""

    def __init__(self, vars, owner=None, doc=None, resolve=None, range_cells=None, resolve_ambiguity=None):   # noqa: A002
        self.vars = vars
        self.owner = owner
        self.doc = doc
        self.resolve = resolve
        self.range_cells = range_cells
        self.resolve_ambiguity = resolve_ambiguity

    def cell(self, addr):
        """The value of a cell of a range, or MISSING."""
        return self.vars.get(addr, MISSING)

    def cells(self, n):
        """The cells of Range n: [(addr, value, kind)], kind None when the hook does not say."""
        if self.range_cells is not None:
            got = self.range_cells(n)
            if got is not None:
                return list(got)
        out = []
        for addr in range_cells(n):
            v = self.cell(addr)
            if v is not MISSING:
                out.append((addr, v, None))
        return out


_property_value = P.property_value


def _rt(message):
    return ExprError(message, "RuntimeError")


def _ref_text(r):
    return f"<<{r.name}>>" if r.str else r.name


def _resolve_property(n, env):
    owner = env.owner or ""
    doc = env.doc or ""
    p = n.path
    if env.resolve is not None and ((p.doc is not None and p.doc.name != doc) or (p.obj is not None and p.obj.name != owner)
                                    or (len(p.names) >= 2 and p.names[0] not in env.vars)):
        value, rest = env.resolve(p)
        return _property_value(value), list(rest)
    if p.doc is not None and p.doc.name != doc:
        raise _rt(f"Document '{_ref_text(p.doc)}' not found in '{p.doc.name}'")
    if p.obj is not None and p.obj.name != owner:
        raise _rt(f"Document object '{_ref_text(p.obj)}' not found in '{doc}'")
    prop = p.names[0]
    if prop not in env.vars:
        raise _rt(f"Property '{prop}' not found in '{owner}'")
    return _property_value(env.vars[prop]), p.names[1:]


def _map_item(v, key):
    """Py::Mapping(obj).getItem(key) with a string key."""
    if type(v) is str:
        raise P.type_error("string indices must be integers, not 'str'")
    if type(v) in (list, tuple):
        raise P.type_error(f"{type(v).__name__} indices must be integers or slices, not str")
    raise P.type_error(f"PyCXX: Error creating object of type N2Py7MapBaseINS_6ObjectEEE from {py_repr(v)}")


def _apply_id_comp(c, v):
    t = type(c)
    if t is IdAttr:
        return P.get_attr(v, c.name)
    if t is IdIndex:
        return P.get_item(v, c.i)
    if t is IdKey:
        return _map_item(v, c.key)
    return P.get_slice(v, c.b, c.e, None if c.s == 1 else c.s)


def _wrap_comp(owner, f):
    try:
        return f()
    except ExprError as e:
        if "\nin expression: " not in e.message:
            raise ExprError(_in_expr(e.message, owner), e.etype, e.kind) from None
        raise


def _apply_expr_comp(owner, c, v, env):
    """Expression::Component::get: an index or a slice by expressions, with the owner's text on an error."""
    if type(c) is ExprAttr:
        return P.get_attr(v, c.name)
    if not c.range and c.e2 is None and c.e3 is None:
        index = evaluate(c.e1, env)

        def get():
            if type(v) in (str, list, tuple):
                return P.get_item(v, index)
            if not P.is_int_like(index):
                raise P.type_error(f"'{P.type_name(index)}' object cannot be interpreted as an integer")
            return P.get_item(v, index)
        return _wrap_comp(owner, get)
    a = evaluate(c.e1, env) if c.e1 is not None else None
    b = evaluate(c.e2, env) if c.e2 is not None else None
    s = evaluate(c.e3, env) if c.e3 is not None else None

    def sl():
        if type(v) not in (str, list, tuple):
            raise P.type_error(f"'{P.type_name(v)}' object is not subscriptable")
        return P.get_slice(v, a, b, s)
    return _wrap_comp(owner, sl)


def _eval_var(n, env):
    v, rest = _resolve_property(n, env)
    for name in rest:
        v = P.get_attr(v, name)
    for c in n.path.sub:
        v = _apply_id_comp(c, v)
    for c in n.comps:
        v = _apply_expr_comp(n, c, v, env)
    return v


def _with_expr(n, f, *args):
    try:
        return f(*args)
    except ExprError as e:
        if not e.raw and "\nin expression: " not in e.message:
            raise ExprError(_in_expr(e.message, n), e.etype, e.kind) from None
        raise


_TO_BIN = {"+": "add", "-": "sub", "*": "mul", "/": "div", "%": "mod", "^": "pow", "unit": "mul"}
_TO_CMP = {"==": "eq", "!=": "ne", "<": "lt", "<=": "le", ">": "gt", ">=": "ge"}


def _supported(a):
    return P.is_numeric(a) or type(a) in (str, list) or isinstance(a, Other)


def _calc(n, o, left, right, env):
    """OperatorExpression's calc(): for security only numbers, strings and lists are accepted, then Python's operators run."""
    lv = evaluate(left, env)
    if not _supported(lv):
        raise ExprError(_in_expr("Unsupported operator", n), "TypeError")
    if o == "pos":
        return _with_expr(n, P.pos, lv)
    if o == "neg":
        return _with_expr(n, P.neg, lv)
    rv = evaluate(right, env)
    if (o != "%" or type(lv) is not str) and not _supported(rv):
        raise ExprError(_in_expr("Unsupported operator", n), "TypeError")
    cmp = _TO_CMP.get(o)
    if cmp:
        return _with_expr(n, P.compare, lv, rv, cmp)
    return _with_expr(n, P.binary, _TO_BIN[o], lv, rv)


def _ev_const(n, env):
    if n.name == "None":
        return None
    if n.name == "True":
        return True
    if n.name == "False":
        return False
    return P.from_quantity(Quantity(n.v, ZERO))


def _ev_str(n, env):
    if n.bad:
        raise ExprError(n.bad, "UnicodeDecodeError", "eval", True)
    return n.s


def _ev_cond(n, env):
    return evaluate(n.t, env) if P.truth(evaluate(n.c, env)) else evaluate(n.f, env)


_EVAL = {
    Num: lambda n, env: P.from_quantity(Quantity(n.v, ZERO)),
    Const: _ev_const,
    UnitNode: lambda n, env: P.from_quantity(n.q),
    Str: _ev_str,
    Var: _eval_var,
    Neg: lambda n, env: _calc(n, "neg", n.a, None, env),
    Pos: lambda n, env: _calc(n, "pos", n.a, None, env),
    Op: lambda n, env: _calc(n, n.op, n.l, n.r, env),
    Cond: _ev_cond,
    Range: lambda n, env: _range_list(n, env),
    Fn: lambda n, env: _fn.eval_function(n, env),
}


def evaluate(n, env):
    """Evaluate a tree against the owner's properties (FreeCAD's getPyValue): a Python value."""
    return _EVAL[type(n)](n, env)


# ─── Cell ranges (RangeExpression) ─────────────────────────────────────────────────────────────

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
        raise ExprError(_in_expr(f"Invalid cell range {n.a}:{n.b}", n), "ExpressionError")
    return [f"{column_name(c)}{r}" for r in range(min(c1[0], c2[0]), max(c1[0], c2[0]) + 1)
            for c in range(min(c1[1], c2[1]), max(c1[1], c2[1]) + 1)]


def _range_list(n, env):
    return [_property_value(v) for _, v, _ in env.cells(n)]


# ─── What the quantity boxes and the callers use ─────────────────────────────────────────────────

def as_quantity(v):
    """The result as a quantity: a number, a Quantity or a bool; anything else is not a quantity."""
    if isinstance(v, Quantity):
        return v
    if type(v) is float:
        return Quantity(v, ZERO)
    if type(v) is int:
        return Quantity(P.float_of_int(v), ZERO)
    if type(v) is bool:
        return Quantity(1.0 if v else 0.0, ZERO)
    raise QuantityError("Expression could not be evaluated", "eval")


def _deep(f, *args):
    """A tree nested deeper than Python's stack stops with the error Python gives for it."""
    try:
        return f(*args)
    except RecursionError:
        raise _recursion() from None


def eval_node(n, vars, owner=None):   # noqa: A002
    """Evaluate a tree to a quantity (Expression::eval())."""
    return as_quantity(_deep(evaluate, n, Env(vars, owner)))


def evaluate_value(text, env):
    """Evaluate an expression (without its leading "=") to a Python value."""
    return _deep(lambda: evaluate(parse(text, frozenset(env.vars), env.owner, resolve_ambiguity=env.resolve_ambiguity), env))


def evaluate_quantity(text, vars, owner=None):   # noqa: A002
    """Evaluate an expression (without its leading "=") to a quantity; `vars` are the names it may use."""
    return eval_node(parse(text, frozenset(vars), owner), vars, owner)


def result_text(v):
    """What Expression Editor shows for a result that is not a number (result->toString())."""
    return quote(v) if type(v) is str else py_str(v)


def has_additive(n):
    """AdditiveOperatorDetector: whether the input has a + or - between terms, anywhere in the tree."""
    t = type(n)
    if t is Op:
        return n.op in ("+", "-") or has_additive(n.l) or has_additive(n.r)
    if t is Neg or t is Pos:
        return has_additive(n.a)
    if t is Fn:
        return any(has_additive(a) for a in n.args)
    if t is Cond:
        return has_additive(n.c) or has_additive(n.t) or has_additive(n.f)
    if t is Var:
        return any(type(c) is ExprIndex and any(e is not None and has_additive(e) for e in (c.e1, c.e2, c.e3)) for c in n.comps)
    return False


def rewrite_ownerless(n):
    """rewriteOwnerlessQuantityExpression: in a quantity field "1/2 mm" means (1/2) mm."""
    t = type(n)
    if t is Neg or t is Pos:
        return t(rewrite_ownerless(n.a))
    if t is not Op:
        return n
    lt, rt = rewrite_ownerless(n.l), rewrite_ownerless(n.r)
    if n.op == "/" and type(rt) is Op and rt.op == "unit":
        return Op("*", Op("/", lt, rt.l), rt.r)
    return Op(n.op, lt, rt)


def apply_default_unit(n, unit, vars=None, symbol=""):   # noqa: A002
    """applyDefaultUnitPolicy: at each + or - from the top, a whole term without a unit takes the field's unit."""
    vars = {} if vars is None else vars
    if type(n) is not Op or n.op not in ("+", "-"):
        return n

    def side(o):
        try:
            q = eval_node(o, vars)
            if P.is_dimless(q.dims):
                return Op("unit", o, UnitNode(unit, symbol))
        except QuantityError:
            pass   # a nested sum may need its own terms given the unit first
        return apply_default_unit(o, unit, vars, symbol) if type(o) is Op and o.op in ("+", "-") else o
    return Op(n.op, side(n.l), side(n.r))


def identifiers(n):
    """Every VarPath the tree reads (Expression::getIdentifiers), in order; a Range gives one VarPath per cell (or its two ends,
    when they are not cell addresses: an alias)."""
    out = []

    def walk(x):
        t = type(x)
        if t is Var:
            out.append(x.path)
            for c in x.comps:
                if type(c) is ExprIndex:
                    for e in (c.e1, c.e2, c.e3):
                        if e is not None:
                            walk(e)
        elif t is Range:
            try:
                out.extend(VarPath(names=[a]) for a in range_cells(x))
            except ExprError:
                out.extend((VarPath(names=[x.a]), VarPath(names=[x.b])))
        elif t is Neg or t is Pos:
            walk(x.a)
        elif t is Op:
            walk(x.l)
            walk(x.r)
        elif t is Fn:
            for a in x.args:
                walk(a)
        elif t is Cond:
            walk(x.c)
            walk(x.t)
            walk(x.f)
    _deep(walk, n)
    return out


from . import fcexpr_fn as _fn  # noqa: E402  (the functions use the evaluator above)


def walk(n):
    """Every node of the tree, the root first (what an ExpressionVisitor visits): the operands, the arguments, the
    expressions of a name's indexers."""
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


def copy(n):
    """Expression::copy."""
    import copy as _copy
    return _copy.deepcopy(n)
