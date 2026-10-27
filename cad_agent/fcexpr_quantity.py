# SPDX-License-Identifier: LGPL-2.1-or-later
# Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
# LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
#   src/Base/Quantity.l: 2013 Jürgen Riegel
#   src/Base/Quantity.y: 2013 Jürgen Riegel
#   src/Base/Quantity.cpp: 2013 Jürgen Riegel
#   src/Mod/Measure/Gui/TaskMassProperties.cpp: 2026 Morten Vajhøj
#   No copyright line in the file: src/Base/Unit.h, src/Base/Unit.cpp, src/Base/NumericFormatting.cpp,
#   src/Base/UnitsConvData.h, src/Base/UnitsSchemasData.h
"""FreeCAD's quantities for the Python formula engine (cad_agent/fcexpr.py), a port of ui/src/quantity.ts: the Quantity.l lexer
and Quantity.y grammar (parse_quantity), Unit::getString and getTypeString, Quantity::toNumber, and UnitsSchema::translate with
its special formatters (user_string). Values are in FreeCAD's internal units: mm, kg, s, A, K, mol, cd, degree.

The tables (units, unit types, schemas, the expression grammar) are in fcexpr_data.json, which ui/scripts/fcexprpy.py writes
from the TypeScript sources."""
import json
import math
from decimal import ROUND_HALF_EVEN, Context, Decimal
from pathlib import Path

DATA = json.loads((Path(__file__).with_name("fcexpr_data.json")).read_text(encoding="utf-8"))

ZERO = (0, 0, 0, 0, 0, 0, 0, 0)
ANGLE = (0, 0, 0, 0, 0, 0, 0, 1)
LENGTH = (1, 0, 0, 0, 0, 0, 0, 0)
DBL_MIN = 2.2250738585072014e-308
EPSILON = 2.220446049250313e-16
SYMBOLS = ("mm", "kg", "s", "A", "K", "mol", "cd", "deg")

#: Each token the quantity lexer knows: its value in internal units and its dimensions.
UNITS = {k: (float(v), tuple(d)) for k, (v, d) in DATA["units"].items()}
#: Unit::getTypeString: the named quantity types, first match wins.
UNIT_TYPES = [(name, tuple(d)) for name, d in DATA["unit_types"]]
#: The unit systems as UnitsApi::getDescriptions lists them: by number.
SCHEMAS = sorted(DATA["schemas"], key=lambda s: s["num"])
_TYPE_OF = {}
for _name, _d in UNIT_TYPES:
    _TYPE_OF.setdefault(_d, _name)


class QuantityError(Exception):
    """A parse failure ('syntax'), Base::UnitsMismatchError ('mismatch') or another evaluation error ('eval')."""

    def __init__(self, message, kind="syntax"):
        super().__init__(message)
        self.message = message
        self.kind = kind

    def __str__(self):
        return self.message


class Quantity:
    """Base::Quantity: a value in internal units and the eight exponents of its unit. Python's operators on it follow
    Base/QuantityPyImp.cpp (fcexpr_py.binary and compare)."""
    __slots__ = ("value", "dims")

    def __init__(self, value, dims=ZERO):
        self.value = float(value)
        self.dims = tuple(dims)

    def __repr__(self):
        from .fcexpr_py import py_repr
        return py_repr(self)

    __str__ = __repr__

    def __hash__(self):
        return hash((self.value, self.dims))

    @property
    def Value(self):   # noqa: N802 (FreeCAD's name)
        return self.value

    @property
    def unit_string(self):
        return unit_string(self.dims)

    @property
    def user_string(self):
        return user_string(self)[0]


def _install_operators():
    from . import fcexpr_py as P

    def binop(op, swap=False):
        return (lambda a, b: P.binary(op, b, a)) if swap else (lambda a, b: P.binary(op, a, b))

    for name, op in (("add", "add"), ("sub", "sub"), ("mul", "mul"), ("truediv", "div"), ("mod", "mod"), ("pow", "pow")):
        setattr(Quantity, f"__{name}__", binop(op))
        setattr(Quantity, f"__r{name}__", binop(op, True))
    for name in ("eq", "ne", "lt", "le", "gt", "ge"):
        setattr(Quantity, f"__{name}__", (lambda op: lambda a, b: P.compare(a, b, op))(name))
    Quantity.__neg__ = P.neg
    Quantity.__pos__ = P.pos
    Quantity.__bool__ = lambda a: a.value != 0
    Quantity.__hash__ = lambda a: hash((a.value, a.dims))


# ─── libm as C has it: no exceptions, a NaN or an infinity instead ───────────────────────────────────

def _safe(f, overflow=math.inf):
    def g(x):
        try:
            return f(x)
        except OverflowError:
            return overflow if not callable(overflow) else overflow(x)
        except ValueError:
            return math.nan
    return g


def c_log(x):
    if x == 0:
        return -math.inf
    if x < 0 or math.isnan(x):
        return math.nan
    return math.log(x)


def c_log10(x):
    if x == 0:
        return -math.inf
    if x < 0 or math.isnan(x):
        return math.nan
    return math.log10(x)


c_acos = _safe(math.acos)
c_asin = _safe(math.asin)
c_atan = math.atan
c_exp = _safe(math.exp)
c_sin = _safe(math.sin)
c_cos = _safe(math.cos)
c_tan = _safe(math.tan)
c_sinh = _safe(math.sinh, lambda x: math.copysign(math.inf, x))
c_cosh = _safe(math.cosh)
c_tanh = math.tanh
c_sqrt = _safe(math.sqrt)
c_cbrt = math.cbrt if hasattr(math, "cbrt") else (lambda x: math.copysign(abs(x) ** (1 / 3), x))


def c_floor(x):
    return math.copysign(float(math.floor(x)), x) if math.isfinite(x) else x


def c_ceil(x):
    return math.copysign(float(math.ceil(x)), x) if math.isfinite(x) else x


def c_fmod(x, y):
    try:
        return math.fmod(x, y)
    except ValueError:
        return math.nan


def js_round(x):
    """JavaScript's Math.round: to the nearest, a tie toward +infinity."""
    if not math.isfinite(x):
        return x
    r = math.floor(x)
    return float(r + 1 if x - r >= 0.5 else r)


def _is_odd_integer(y):
    return math.isfinite(y) and y == math.floor(y) and abs(math.fmod(y, 2)) == 1


def exact_pow(x, n):
    """x ** n for a whole n, rounded once (x = m * 2^e exactly); None if the answer is not a normal double."""
    m, e = math.frexp(x)
    m = int(m * (1 << 53))
    e -= 53
    k = abs(n)
    mk = m ** k
    E = e * k
    try:
        if n >= 0:
            r = mk * 2 ** E if E >= 0 else mk / (1 << -E)
        else:
            r = 1 / (mk << E) if E >= 0 else (1 << -E) / mk
        r = float(r)
    except (OverflowError, ZeroDivisionError):
        return None
    return r if math.isfinite(r) and abs(r) >= DBL_MIN else None


def cpow(x, y):
    """C's pow(): the special cases of C99, and a whole power of a double rounded once."""
    x = float(x)
    y = float(y)
    if x == 1 or y == 0:
        return 1.0
    if x == -1 and math.isinf(y):
        return 1.0
    if math.isfinite(y) and y == math.floor(y) and abs(y) <= 128 and math.isfinite(x) and x != 0:
        r = exact_pow(x, int(y))
        if r is not None:
            return r
    try:
        return math.pow(x, y)
    except OverflowError:
        return -math.inf if x < 0 and _is_odd_integer(y) else math.inf
    except ValueError:
        if x == 0:
            return math.copysign(math.inf, x) if _is_odd_integer(y) else math.inf
        return math.nan


# ─── Quantity.l / Quantity.y ───────────────────────────────────────────────────────────────────

_FUNCS = {"acos": c_acos, "asin": c_asin, "atan": c_atan, "abs": abs, "exp": c_exp, "log": c_log, "log10": c_log10,
          "sin": c_sin, "sinh": c_sinh, "tan": c_tan, "tanh": c_tanh, "sqrt": c_sqrt, "cos": c_cos}
_DEAD = ("atan2", "mod", "pow")
_WORDS = list(UNITS) + list(_FUNCS) + list(_DEAD) + ["pi", "e"]
_JS_SPACE = set("\t\n\v\f\r       　﻿") | {chr(c) for c in range(0x2000, 0x200b)}


def _digits(text, i):
    j = i
    while j < len(text) and "0" <= text[j] <= "9":
        j += 1
    return j


def _number_at(text, i, sep):
    """The longest of Quantity.l's number rules {DIGIT}+sep?{DIGIT}*{EXPO}? and sep?{DIGIT}+{EXPO}? at i, or ''."""
    def expo(j):
        if j < len(text) and text[j] in "eE":
            k = j + 1
            if k < len(text) and text[k] in "+-":
                k += 1
            m = _digits(text, k)
            if m > k:
                return m
        return j
    best = i
    j = _digits(text, i)
    if j > i:   # {DIGIT}+ sep? {DIGIT}*
        k = j
        if k < len(text) and text[k] == sep:
            k = _digits(text, k + 1)
        best = max(best, expo(k))
    k = i + 1 if i < len(text) and text[i] == sep else i
    m = _digits(text, k)
    if m > k:
        best = max(best, expo(m))
    return text[i:best]


def _lex(text):
    out = []
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == "[":
            j = text.find("]", i)
            if j < 0:
                raise QuantityError("Unterminated quantity comment")
            i = j + 1
            continue
        if c in _JS_SPACE:
            i += 1
            continue
        best, tok = "", None
        for w in _WORDS:
            if len(w) > len(best) and text.startswith(w, i):
                best = w
                if w in UNITS:
                    tok = ("UNIT", Quantity(*UNITS[w]))
                elif w == "pi":
                    tok = ("NUM", math.pi)
                elif w == "e":
                    tok = ("NUM", math.e)
                else:
                    tok = ("FN", w)
        for sep in (".", ","):
            m = _number_at(text, i, sep)
            if len(m) > len(best):
                best = m
                tok = ("NUM", float(m.replace(",", ".", 1)))
        if best == "1":
            tok = ("ONE", 1.0)
        if tok is None:
            if c in "+()=/*^":
                best, tok = c, (c, None)
            elif c in "-−":
                best, tok = c, ("-", None)
            elif ord(c) >= 0x80:   # a signed char below zero: bison's end of input, the rest is ignored
                break
            else:
                raise QuantityError("syntax error")
        out.append(tok)
        i += len(best)
    return out


def _check_range(dims):
    for d in dims:
        if d >= 8:
            raise QuantityError("Unit exponent overflow", "eval")
        if d < -8:
            raise QuantityError("Unit exponent underflow", "eval")
    return tuple(dims)


def _qmul(a, b):
    return Quantity(a.value * b.value, _check_range([x + y for x, y in zip(a.dims, b.dims)]))


def _qdiv(a, b):
    return Quantity(js_div(a.value, b.value), _check_range([x - y for x, y in zip(a.dims, b.dims)]))


def _to_int8(x):
    if not math.isfinite(x):
        return 0
    t = int(x)
    if t > 2147483647 or t < -2147483648:
        return 0
    t &= 0xff
    return t - 256 if t >= 128 else t


def _qpow(a, e):
    nn = _to_int8(e)
    return Quantity(cpow(a.value, e), _check_range([d * nn for d in a.dims]))


def js_div(a, b):
    """a / b as IEEE does it (Python raises on a zero divisor)."""
    try:
        return a / b
    except ZeroDivisionError:
        if a == 0 or math.isnan(a):
            return math.nan
        return math.copysign(math.inf, a) * math.copysign(1, b)


_PREC = {"+": 1, "-": 1, "*": 2, "/": 2, "^": 4}


def parse_quantity(text):
    """Quantity.y: a number, a unit, or up to three quantities added (num unit, num / unit). Raises QuantityError."""
    toks = _lex(text)
    if not toks:
        return Quantity(DBL_MIN, ZERO)
    p = [0]

    def peek(k=None):
        k = p[0] if k is None else k
        return toks[k] if k < len(toks) else None

    def t_at(k):
        t = peek(k)
        return t[0] if t else None

    def eat(t):
        if t_at(p[0]) != t:
            raise QuantityError("syntax error")
        p[0] += 1
        return toks[p[0] - 1]

    def starts_unit(k=None):
        k = p[0] if k is None else k
        t = t_at(k)
        return t == "UNIT" or (t == "(" and starts_unit(k + 1)) or (t == "ONE" and t_at(k + 1) == "/" and starts_unit(k + 2))

    def num_primary():
        t = peek()
        if not t:
            raise QuantityError("syntax error")
        if t[0] in ("NUM", "ONE"):
            p[0] += 1
            return t[1]
        if t[0] in ("+", "-"):
            p[0] += 1
            v = num_expr(3)
            return -v if t[0] == "-" else v
        if t[0] == "(":
            p[0] += 1
            v = num_expr(0)
            eat(")")
            return v
        if t[0] == "FN":
            if t[1] not in _FUNCS:
                raise QuantityError("syntax error")
            p[0] += 1
            eat("(")
            v = num_expr(0)
            eat(")")
            return float(_FUNCS[t[1]](v))
        raise QuantityError("syntax error")

    def num_expr(lo):
        left = num_primary()
        while True:
            t = t_at(p[0])
            if t is None or t not in _PREC or _PREC[t] < lo:
                return left
            if t == "/" and starts_unit(p[0] + 1):
                return left
            p[0] += 1
            right = num_expr(_PREC[t] if t == "^" else _PREC[t] + 1)
            a, b = left, right
            left = a + b if t == "+" else a - b if t == "-" else a * b if t == "*" else js_div(a, b) if t == "/" else cpow(a, b)

    def unit_primary():
        t = peek()
        if t and t[0] == "UNIT":
            p[0] += 1
            return t[1]
        if t and t[0] == "ONE" and t_at(p[0] + 1) == "/":
            p[0] += 2
            return _qdiv(Quantity(1.0, ZERO), unit_expr(3))
        if t and t[0] == "(":
            p[0] += 1
            u = unit_expr(0)
            eat(")")
            return u
        raise QuantityError("syntax error")

    def unit_expr(lo):
        left = unit_primary()
        while True:
            t = t_at(p[0])
            if t is None:
                return left
            if t == "^" and 4 >= lo:
                p[0] += 1
                left = _qpow(left, num_expr(4))
                continue
            if t in ("*", "/") and 2 >= lo and starts_unit(p[0] + 1):
                p[0] += 1
                r = unit_expr(3)
                left = _qmul(left, r) if t == "*" else _qdiv(left, r)
                continue
            return left

    def quantity():
        if starts_unit():
            return "unit", unit_expr(0)
        n = Quantity(num_expr(0), ZERO)
        if peek() is None:
            return "num", n
        if t_at(p[0]) == "/" and starts_unit(p[0] + 1):
            p[0] += 1
            return "quantity", _qdiv(n, unit_expr(0))
        if starts_unit():
            return "quantity", _qmul(n, unit_expr(0))
        raise QuantityError("syntax error")

    kind, first = quantity()
    if kind != "quantity":
        if p[0] < len(toks):
            raise QuantityError("syntax error")
        return first
    total = first
    k = 1
    while k < 3 and p[0] < len(toks):
        kind, nxt = quantity()
        if kind != "quantity":
            raise QuantityError("syntax error")
        if total.dims != nxt.dims:
            raise QuantityError("Quantity::operator +(): Unit mismatch in plus operation", "mismatch")
        total = Quantity(total.value + nxt.value, total.dims)
        k += 1
    if p[0] < len(toks):
        raise QuantityError("syntax error")
    return total


# ─── Unit::getString, getTypeString ──────────────────────────────────────────────────────────────

def type_string(dims):
    """Unit::getTypeString: the name of the quantity type, or ''."""
    return _TYPE_OF.get(tuple(dims), "")


def unit_string(dims):
    """Unit::getString: mm^2, kg/(mm*s^2), 1/mm."""
    def part(i):
        return SYMBOLS[i] if abs(dims[i]) <= 1 else f"{SYMBOLS[i]}^{abs(dims[i])}"
    pos = [i for i, d in enumerate(dims) if d > 0]
    neg = [i for i, d in enumerate(dims) if d < 0]
    numr = "*".join(part(i) for i in pos)
    if not neg:
        return numr
    den = "*".join(part(i) for i in neg)
    return f"{numr or '1'}/{'(' + den + ')' if len(neg) > 1 else den}"


# ─── Numbers as text ─────────────────────────────────────────────────────────────────────────────

_CTX = Context(prec=2000)


def _sign(v):
    return "-" if v < 0 or (v == 0 and math.copysign(1, v) < 0) else ""


def to_number(v, fmt="Default", precision=6):
    """Quantity::toNumber: a std::stringstream at setprecision(precision), std::fixed ('Fixed'), std::scientific
    ('Scientific') or the default float format ('Default'): printf's %.*f, %.*e and %.*g of the double's exact value."""
    v = float(v)
    if not math.isfinite(v):
        return "nan" if math.isnan(v) else "-inf" if v < 0 else "inf"
    code = {"Fixed": "f", "Scientific": "e", "Default": "g"}[fmt]
    return "%.*{}".format(code) % (precision, v)


def format_fixed(v, decimals):
    """Base::formatNumericValue with QuantityFormat::Fixed: ICU rounds the double's shortest round-trip digits half to even, no
    grouping; the minus sign stays on negative zero and on negative numbers that round to zero."""
    v = float(v)
    if not math.isfinite(v):
        return "NaN" if math.isnan(v) else "Infinity" if v > 0 else "-Infinity"
    d = Decimal(repr(abs(v)))
    q = d.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_EVEN, context=_CTX)
    return _sign(v) + format(q, "f")


def js_num_str(x):
    """JavaScript's String(number)."""
    x = float(x)
    if math.isnan(x):
        return "NaN"
    if math.isinf(x):
        return "Infinity" if x > 0 else "-Infinity"
    if x == 0:
        return "0"
    s = repr(abs(x))
    mant, _, exp = s.partition("e")
    digits = mant.replace(".", "")
    point = mant.index(".") if "." in mant else len(mant)
    lead = len(digits) - len(digits.lstrip("0"))
    digits = digits.strip("0") or "0"
    k = point - lead + (int(exp) if exp else 0)   # the decimal point after k digits
    n = len(digits)
    if n <= k <= 21:
        out = digits + "0" * (k - n)
    elif 0 < k <= 21:
        out = digits[:k] + "." + digits[k:]
    elif -6 < k <= 0:
        out = "0." + "0" * (-k) + digits
    else:
        e = k - 1
        out = digits[0] + ("." + digits[1:] if n > 1 else "") + "e" + ("+" if e >= 0 else "-") + str(abs(e))
    return ("-" if x < 0 else "") + out


# ─── UnitsSchema::translate ──────────────────────────────────────────────────────────────────────

def _to_fractional(value, denominator):
    n = int(js_round((abs(value) / 25.4) * denominator))
    if n == 0:
        return "0"
    feet = n // (12 * denominator)
    n -= 12 * denominator * feet
    inches = n // denominator
    numerator = n - denominator * inches
    g = math.gcd(numerator, denominator)
    numerator //= g
    den = denominator // g
    out = "-" if value < 0 else ""
    space = False
    if feet > 0:
        out += f"{feet}'"
        space = True
    if inches > 0:
        out += f"{' ' if space else ''}{inches}\""
        space = False
    if numerator > 0:
        if inches > 0:
            out += f" {'-' if value < 0 else '+'} "
            space = False
        out += f"{' ' if space else ''}{numerator}/{den}\""
    return out


def _to_dms(value):
    def split(t):
        w = c_floor(t)
        return w, 60 * (t - w)
    deg, mins = split(value)
    out = f"{js_num_str(deg)}°"
    if mins > 0:
        m, secs = split(mins)
        out += f"{js_num_str(m)}′"
        if secs > 0:
            out += f"{js_num_str(js_round(secs))}″"
    return out


#: UnitsApi's current schema, decimals and fraction denominator (Preferences > General > Units).
UNIT_PREFS = {"schema": 0, "decimals": 2, "denominator": 8}


def user_string(q, schema=None, decimals=None, denominator=None):
    """UnitsSchema::translate: the quantity as the schema shows it ("12.50 mm", "1.25 m"). Returns (text, factor, unit).
    `q` is a Quantity or a text parse_quantity reads."""
    if isinstance(q, str):
        q = parse_quantity(q)
    schema = UNIT_PREFS["schema"] if schema is None else schema
    decimals = UNIT_PREFS["decimals"] if decimals is None else decimals
    denominator = UNIT_PREFS["denominator"] if denominator is None else denominator
    spec = next((s for s in SCHEMAS if s["num"] == schema), SCHEMAS[0])
    factor, unit = 1.0, unit_string(q.dims)
    rows = spec["specs"].get(type_string(q.dims))
    if rows:
        mag = abs(q.value)
        row = next((r for r in rows if r[0] * (1 - 1e-12) > mag or r[0] == 0), None)
        if row is None:
            raise QuantityError(f"Suitable threshold not found. Schema: {spec['name']} value: {js_num_str(q.value)}", "eval")
        if row[2] == 0:
            if row[1] == "toFractional":
                return _to_fractional(q.value, denominator), 25.4, "in"
            if row[1] == "toDMS":
                return _to_dms(q.value), 1.0, "deg"
        else:
            factor, unit = float(row[2]), row[1]
    s = format_fixed(js_div(q.value, factor), decimals)
    bare = not unit or unit in ("°", "″", "′", '"', "'")
    return f"{s}{'' if bare else ' '}{unit}", factor, unit


def format_mass_property(value, dims, schema=None, decimals=None, denominator=None):
    """TaskMassProperties.cpp's setText: below Precision::Confusion a value shows as zero."""
    return user_string(Quantity(0.0 if abs(value) < 1e-7 else value, dims), schema, decimals, denominator)[0]
