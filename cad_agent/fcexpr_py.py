# SPDX-License-Identifier: LGPL-2.1-or-later
# Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
# LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
#   src/App/Expression.cpp: 2015 Eivind Kvedalen
#   src/Base/Exception.cpp: 2002 Jürgen Riegel
#   src/Base/Quantity.cpp: 2013 Jürgen Riegel
#   src/Base/QuantityPyImp.cpp: 2013 Jürgen Riegel
#   src/Base/VectorPyImp.cpp: 2008 Werner Mayer
#   No copyright line in the file: src/Base/Unit.cpp, src/Base/Unit.h
"""The values FreeCAD's expressions are made of, for cad_agent/fcexpr.py (a port of ui/src/expr-py.ts).

FreeCAD evaluates an expression through Python objects: OperatorExpression's calc() runs PyNumber_Add and its kin on whatever
the operands are, so what an operator does depends on the Python types of its operands. Here the values are Python's own (int,
float, bool, str, None, complex, list, tuple) and two classes that follow FreeCAD's: Quantity (Base/QuantityPyImp.cpp: its own
add, remainder, power and comparison, never the other operand's) and Vector (Base/VectorPyImp.cpp); Other stands for what
Python prints but the engine cannot compute with (a Unit). The operations are written out with the messages of FreeCAD's
Python (3.13), so that the answers do not depend on the Python this runs on, and with expr-py.ts's size limits, so that the
server and the browser agree."""
import math

from .fcexpr_quantity import (EPSILON, ZERO, Quantity, QuantityError, _install_operators, cpow, type_string,
                              unit_string, user_string, to_number)

__all__ = ["ExprError", "Quantity", "Vector", "Other", "QUIRKS", "binary", "compare", "neg", "pos", "truth", "py_repr", "py_str"]


class ExprError(QuantityError):
    """An exception as Python reports it: `etype` is the class name FreeCAD raises (ParserError, TypeError, ExpressionError ...),
    `message` its text. `raw`: a Base exception that went through Python's C API without becoming a Python exception, so that
    calc() does not add the "in expression:" line to it (a Quantity comparison between different units is one)."""

    def __init__(self, message, etype, kind="eval", raw=False):
        super().__init__(message, kind)
        self.etype = etype
        self.raw = raw

    def __repr__(self):
        return f"ExprError({self.message!r}, {self.etype!r})"


def mismatch(message):
    """Base::UnitsMismatchError (Python's ArithmeticError)."""
    return ExprError(message, "ArithmeticError", "mismatch")


def type_error(message):
    return ExprError(message, "TypeError")


def overflow(message):
    return ExprError(message, "OverflowError")


def system_error():
    """The SystemError Python raises when a call returned a result with an exception set."""
    return ExprError("<built-in method evalExpression of FeaturePython object at 0x0> returned a result with an exception set",
                     "SystemError", "eval", True)


class _Quirks:
    """Where FreeCAD does something its authors cannot have meant; off here, on for the differential test.
    int32_cast: essentiallyInteger casts an integral double above INT_MAX to int, so on x86 the Python int that comes out of
    3000000000, 1e10 or 2^31 as a number is -2147483648."""
    int32_cast = False


QUIRKS = _Quirks()


class Vector:
    """Base.Vector, a point or direction in mm."""
    __slots__ = ("x", "y", "z")

    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x, self.y, self.z = float(x), float(y), float(z)

    @property
    def v(self):
        return (self.x, self.y, self.z)

    def __iter__(self):
        return iter((self.x, self.y, self.z))

    def __repr__(self):
        return py_repr(self)

    def __eq__(self, other):
        return isinstance(other, Vector) and compare(self, other, "eq")

    def __hash__(self):
        return hash(self.v)


class Other:
    """Something Python prints but this engine cannot compute with (a Unit, a bound method ...)."""
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


# ─── Types ───────────────────────────────────────────────────────────────────────────────────────

def type_name(a):
    """tp_name, as the messages spell it."""
    if isinstance(a, Quantity):
        return "Base.Quantity"
    if isinstance(a, Vector):
        return "Base.Vector"
    if isinstance(a, Other):
        return a.type
    if a is None:
        return "NoneType"
    return type(a).__name__


def is_int_like(a):
    return type(a) is int or type(a) is bool


def is_real(a):
    t = type(a)
    return t is int or t is float or t is bool


def is_numeric(a):
    """PyNumber_Check (a Vector passes it, as it sets the nb_int and nb_float slots)."""
    return is_real(a) or type(a) is complex or isinstance(a, (Quantity, Vector))


def is_dimless(d):
    return not any(d)


# ─── Units (Base/Unit.cpp) ───────────────────────────────────────────────────────────────────────

def check_range(d):
    for e in d:
        if e >= 8:
            raise ExprError("Unit exponent overflow", "OverflowError")
        if e < -8:
            raise ExprError("Unit exponent underflow", "ArithmeticError")
    return tuple(d)


def unit_mul(a, b):
    return check_range([x + y for x, y in zip(a, b)])


def unit_div(a, b):
    return check_range([x - y for x, y in zip(a, b)])


def to_int8(x):
    """static_cast<int8_t>(double) as x86 does it: through a 32-bit integer, whose low byte is kept."""
    if not math.isfinite(x):
        return 0
    t = int(x)
    if t > 2147483647 or t < -2147483648:
        return 0
    t &= 0xff
    return t - 256 if t >= 128 else t


def unit_pow(a, exp):
    """Unit::pow(double)."""
    out = []
    for val in a:
        num = val * exp
        if abs(_js_round_num(num) - num) >= EPSILON:
            raise mismatch("pow() of unit not possible")
        out.append(to_int8(val * exp))
    return check_range(out)


def _js_round_num(x):
    if not math.isfinite(x):
        return x
    r = math.floor(x)
    return float(r + 1 if x - r >= 0.5 else r)


def unit_root(a, n):
    """Unit::root(n) (sqrt() and cbrt())."""
    out = []
    for val in a:
        if math.fmod(val, n) != 0:
            raise mismatch("unit values must be divisible by root")
        out.append(val // n if val >= 0 else -((-val) // n))
    return check_range(out)


# ─── Quantity (Base/Quantity.cpp) ────────────────────────────────────────────────────────────────

def _fdiv(a, b):
    try:
        return a / b
    except ZeroDivisionError:
        if a == 0 or math.isnan(a):
            return math.nan
        return math.copysign(math.inf, a) * math.copysign(1, b)


def _fmul(a, b):
    return a * b


def q_add(a, b):
    if a.dims != b.dims:
        raise mismatch("Quantity::operator +(): Unit mismatch in plus operation")
    return Quantity(a.value + b.value, a.dims)


def q_sub(a, b):
    if a.dims != b.dims:
        raise mismatch("Quantity::operator -(): Unit mismatch in minus operation")
    return Quantity(a.value - b.value, a.dims)


def q_mul(a, b):
    return Quantity(a.value * b.value, unit_mul(a.dims, b.dims))


def q_div(a, b):
    return Quantity(_fdiv(a.value, b.value), unit_div(a.dims, b.dims))


def q_pow_q(a, b):
    """Quantity::pow(const Quantity&): the unit is raised to the exponent cast to signed char."""
    if not is_dimless(b.dims):
        raise mismatch("Quantity::pow(): exponent must not have a unit")
    return Quantity(cpow(a.value, b.value), unit_pow(a.dims, to_int8(b.value)))


def q_pow_d(a, exp):
    return Quantity(cpow(a.value, exp), unit_pow(a.dims, exp))


def q_less(a, b):
    """Quantity::operator<, which the min collector calls directly."""
    if a.dims != b.dims:
        raise ExprError("Quantity::operator <(): quantities need to have same unit to compare", "ArithmeticError", "mismatch", True)
    return a.value < b.value


def q_greater(a, b):
    if a.dims != b.dims:
        raise ExprError("Quantity::operator >(): quantities need to have same unit to compare", "ArithmeticError", "mismatch", True)
    return a.value > b.value


def q_add_assign(a, b):
    """Quantity::operator+= (the sum and average collectors)."""
    if a.dims != b.dims:
        raise mismatch("Quantity::operator +=(): Unit mismatch in plus operation")
    return Quantity(a.value + b.value, a.dims)


def _q_eq(a, b):
    return a.value == b.value and a.dims == b.dims


# ─── Python's numbers ────────────────────────────────────────────────────────────────────────────

def float_of_int(v):
    try:
        return float(v)
    except OverflowError:
        raise overflow("int too large to convert to float") from None


def real_to_float(a):
    return a if type(a) is float else float_of_int(int(a))


def _as_double_or_system_error(a):
    """PyFloat_AsDouble on an int too big for a double fails, unchecked: Python ends the call with a SystemError."""
    try:
        return real_to_float(a)
    except ExprError:
        raise system_error() from None


def int_true_div(a, b):
    if b == 0:
        raise ExprError("division by zero", "ZeroDivisionError")
    try:
        return a / b
    except OverflowError:
        raise overflow("integer division result too large for a float") from None


def int_mod(a, b):
    if b == 0:
        raise ExprError("integer modulo by zero", "ZeroDivisionError")
    return a % b


def float_mod(vx, wx):
    if wx == 0:
        raise ExprError("float modulo by zero", "ZeroDivisionError")
    try:
        mod = math.fmod(vx, wx)
    except ValueError:
        mod = math.nan
    if mod != 0 or math.isnan(mod):
        if (wx < 0) != (mod < 0) and not math.isnan(mod):
            mod += wx
    else:
        mod = math.copysign(0.0, wx)
    return mod


def _is_odd_integer(x):
    return math.isfinite(x) and x == math.floor(x) and abs(math.fmod(x, 2)) == 1


def float_pow(iv, iw):
    """float_pow (Objects/floatobject.c): the special cases are Python's, the rest is libm's pow()."""
    if iw == 0:
        return 1.0
    if math.isnan(iv):
        return iv
    if math.isnan(iw):
        return 1.0 if iv == 1 else iw
    if math.isinf(iw):
        iv = abs(iv)
        if iv == 1:
            return 1.0
        return abs(iw) if (iw > 0) == (iv > 1) else 0.0
    if math.isinf(iv):
        odd = _is_odd_integer(iw)
        if iw > 0:
            return iv if odd else abs(iv)
        return math.copysign(0.0, iv) if odd else 0.0
    if iv == 0:
        odd = _is_odd_integer(iw)
        if iw < 0:
            raise ExprError("0.0 cannot be raised to a negative power", "ZeroDivisionError")
        return iv if odd else 0.0
    negate = False
    if iv < 0:
        if iw != math.floor(iw):
            return complex_pow(complex(iv, 0), complex(iw, 0))
        iv = -iv
        negate = _is_odd_integer(iw)
    if iv == 1:
        return -1.0 if negate else 1.0
    ix = cpow(iv, iw)
    if math.isinf(ix):
        raise overflow("(34, 'Result too large')")
    return -ix if negate else ix


def complex_pow(a, b):
    """_Py_c_pow."""
    if b.real == 0 and b.imag == 0:
        return complex(1, 0)
    if a.real == 0 and a.imag == 0:
        if b.imag != 0 or b.real < 0:
            raise ExprError("0.0 to a negative or complex power", "ZeroDivisionError")
        return complex(0, 0)
    vabs = math.hypot(a.real, a.imag)
    ln = cpow(vabs, b.real)
    at = math.atan2(a.imag, a.real)
    phase = at * b.real
    if b.imag != 0:
        try:
            ln = _fdiv(ln, math.exp(at * b.imag))
        except OverflowError:
            ln = 0.0
        phase += b.imag * (math.log(vabs) if vabs > 0 else -math.inf)
    re = ln * _cos(phase)
    im = ln * _sin(phase)
    if not (math.isfinite(re) and math.isfinite(im)):
        if all(math.isfinite(x) for x in (a.real, a.imag, b.real, b.imag)):
            raise overflow("complex exponentiation")
    return complex(re, im)


def _cos(x):
    try:
        return math.cos(x)
    except ValueError:
        return math.nan


def _sin(x):
    try:
        return math.sin(x)
    except ValueError:
        return math.nan


def _to_c(a):
    return a if type(a) is complex else complex(real_to_float(a), 0.0)


#: The longest string, list or tuple, and the widest % field, an expression may make (as in the browser).
MAX_LENGTH = 10_000_000


def fits(length):
    if length > MAX_LENGTH:
        raise ExprError("result too large to compute here", "MemoryError")
    return length


def int_pow(a, b):
    """int ** int: exact for a non-negative exponent, else the float answer."""
    if b < 0:
        return float_pow(float_of_int(a), float_of_int(b))
    if a == 0 or a == 1 or b == 0:
        return 1 if b == 0 else a
    if a == -1:
        return 1 if b % 2 == 0 else -1
    if abs(a).bit_length() * b > 4_000_000:
        raise ExprError("integer power too large to compute here", "MemoryError")
    return a ** b


# ─── What FreeCAD makes of a number ─────────────────────────────────────────────────────────────

def from_quantity(q):
    """pyFromQuantity: a quantity with a unit stays one; a plain number becomes an int when it is a whole number
    (essentiallyInteger), else a float."""
    if not is_dimless(q.dims):
        return q
    v = q.value
    if math.isfinite(v) and v == math.floor(v):
        if v < 0:
            if v >= -9223372036854775808:
                return int(v)
        elif v <= 2147483647:
            return int(v)
        elif v <= 9223372036854775808:
            return -2147483648 if QUIRKS.int32_cast else int(v)
    return v


def to_quantity(a):
    """pyToQuantity: a Quantity, a float or an int (a bool is one); None for anything else."""
    if isinstance(a, Quantity):
        return a
    if type(a) is float:
        return Quantity(a, ZERO)
    if is_int_like(a):
        v = int(a)
        if v > 9223372036854775807 or v < -9223372036854775808:
            raise overflow("Python int too large to convert to C long")
        return Quantity(float(v), ZERO)
    return None


def property_value(x):
    """A property's value as an expression sees it: a dimensionless Quantity is a float (PropertyFloat)."""
    if isinstance(x, Quantity) and is_dimless(x.dims):
        return x.value
    return x


# ─── Truth, comparison ──────────────────────────────────────────────────────────────────────────

def truth(a):
    """PyObject_IsTrue. A Quantity is true unless its value is zero."""
    if isinstance(a, Quantity):
        return a.value != 0
    if isinstance(a, (Vector, Other)):
        return True
    return bool(a)


_SYM = {"eq": "==", "ne": "!=", "lt": "<", "le": "<=", "gt": ">", "ge": ">="}


def _rel(a, b, op):
    if op == "eq":
        return a == b
    if op == "ne":
        return a != b
    if op == "lt":
        return a < b
    if op == "le":
        return a <= b
    if op == "gt":
        return a > b
    return a >= b


def _cmp_seq(a, b, op):
    if len(a) != len(b) and op in ("eq", "ne"):
        return op == "ne"
    i = 0
    while i < len(a) and i < len(b) and compare(a[i], b[i], "eq"):
        i += 1
    if i >= len(a) or i >= len(b):
        return _rel(len(a), len(b), op)
    if op == "eq":
        return False
    if op == "ne":
        return True
    return compare(a[i], b[i], op)


def compare(a, b, op):
    """PyObject_RichCompareBool(a, b, op) with FreeCAD's types (QuantityPy's richCompare: two quantities by value and unit, a
    Quantity and any other number by value alone). `op` is eq, ne, lt, le, gt or ge."""
    aq, bq = isinstance(a, Quantity), isinstance(b, Quantity)
    if aq and bq:
        if op == "ne":
            return not _q_eq(a, b)
        if op == "lt":
            return q_less(a, b)
        if op == "le":
            return q_less(a, b) or _q_eq(a, b)
        if op == "gt":
            return not q_less(a, b) and not _q_eq(a, b)
        if op == "ge":
            return not q_less(a, b)
        return _q_eq(a, b)
    if isinstance(a, Vector) and isinstance(b, Vector):
        if op not in ("eq", "ne"):
            raise type_error("no ordering relation is defined for Vector")
        eq = all(abs(x - y) <= EPSILON for x, y in zip(a.v, b.v))
        return eq if op == "eq" else not eq
    if (aq and is_numeric(b)) or (bq and is_numeric(a)):
        def dbl(x):
            if isinstance(x, Quantity):
                return x.value
            if type(x) is complex:
                raise type_error("must be real number, not complex")
            if isinstance(x, Vector):
                raise system_error()
            return _as_double_or_system_error(x)
        u1 = dbl(a)
        u2 = dbl(b)
        return _rel(u1, u2, op)
    if is_real(a) and is_real(b):
        return _rel(a, b, op)
    if type(a) is complex or type(b) is complex:
        if (type(a) is complex or is_real(a)) and (type(b) is complex or is_real(b)):
            if op not in ("eq", "ne"):
                raise type_error(f"'{_SYM[op]}' not supported between instances of '{type_name(a)}' and '{type_name(b)}'")
            eq = _to_c(a) == _to_c(b)
            return eq if op == "eq" else not eq
    ta, tb = type(a), type(b)
    if ta is str and tb is str:
        return _rel(a, b, op)
    if (ta is list and tb is list) or (ta is tuple and tb is tuple):
        return _cmp_seq(a, b, op)
    if a is None and b is None:
        if op == "eq":
            return True
        if op == "ne":
            return False
    if isinstance(a, Other) and isinstance(b, Other) and op in ("eq", "ne"):
        return (a.str == b.str) == (op == "eq")
    if op == "eq":
        return False
    if op == "ne":
        return True
    raise type_error(f"'{_SYM[op]}' not supported between instances of '{type_name(a)}' and '{type_name(b)}'")


# ─── Arithmetic ─────────────────────────────────────────────────────────────────────────────────

#: calc() runs PyNumber_InPlaceRemainder for "%", so its message says "%=".
_SYMBOL = {"add": "+", "sub": "-", "mul": "*", "div": "/", "mod": "%=", "pow": "** or pow()"}


def _q_operand(a):
    if isinstance(a, Quantity):
        return a
    q = to_quantity(a) if is_real(a) else None
    if q is None:
        raise type_error(f"Cannot convert {type_name(a)} to Quantity")
    return q


def _quantity_op(op, a, b):
    """QuantityPy's number_*_handler, which Python calls when either operand is a Quantity (the left one first)."""
    if op in ("add", "sub", "mul", "div"):
        x, y = _q_operand(a), _q_operand(b)
        return q_add(x, y) if op == "add" else q_sub(x, y) if op == "sub" else q_mul(x, y) if op == "mul" else q_div(x, y)
    if not isinstance(a, Quantity):
        raise type_error("First arg must be Quantity")
    if op == "mod":
        if isinstance(b, Quantity):
            d2 = b.value
        elif type(b) is float:
            d2 = b
        elif is_int_like(b):
            d2 = to_quantity(b).value
        else:
            raise type_error("Expected quantity or number")
        return Quantity(float_mod(a.value, d2), a.dims)
    if isinstance(b, Quantity):
        return q_pow_q(a, b)
    if type(b) is float:
        return q_pow_d(a, b)
    if is_int_like(b):
        return q_pow_d(a, to_quantity(b).value)
    raise type_error("Expected quantity or number")


def vec_sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vec_add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vec_scale(a, f):
    return (a[0] * f, a[1] * f, a[2] * f)


def vec_dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def vec_cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def vec_length(a):
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def vec_sqr(a):
    return a[0] * a[0] + a[1] * a[1] + a[2] * a[2]


def _vector_op(op, a, b):
    """VectorPy's number handlers, which Python calls when either operand is a Vector."""
    def scalar(x):
        if isinstance(x, Quantity):
            return x.value
        if type(x) is complex:
            raise type_error("must be real number, not complex")
        return _as_double_or_system_error(x)
    av, bv = isinstance(a, Vector), isinstance(b, Vector)
    if op in ("add", "sub"):
        if not av:
            raise type_error("First arg must be Vector")
        if not bv:
            raise type_error("Second arg must be Vector")
        return Vector(*(vec_add(a.v, b.v) if op == "add" else vec_sub(a.v, b.v)))
    if op == "mul":
        if av:
            if bv:
                return vec_dot(a.v, b.v)
            if is_numeric(b):
                return Vector(*vec_scale(a.v, scalar(b)))
            raise type_error("A Vector can only be multiplied by Vector or number")
        if bv and is_numeric(a):
            return Vector(*vec_scale(b.v, scalar(a)))
        if bv:
            raise type_error("A Vector can only be multiplied by Vector or number")
        raise type_error("First or second arg must be Vector")
    if op == "div":
        if av and is_numeric(b):
            if bv:
                raise type_error(f"unsupported operand type(s) for /: '{type_name(a)}' and '{type_name(b)}'")
            d = scalar(b)
            if d == 0:
                raise ExprError(f"'{type_name(a)}' division by zero", "ZeroDivisionError")
            return Vector(a.x / d, a.y / d, a.z / d)
        raise type_error(f"unsupported operand type(s) for /: '{type_name(a)}' and '{type_name(b)}'")
    if op == "mod":
        if av and bv:
            return Vector(*vec_cross(a.v, b.v))
        raise type_error(f"unsupported operand type(s) for %: '{type_name(a)}' and '{type_name(b)}'")
    raise type_error(f"unsupported operand type(s) for ** or pow(): '{type_name(a)}' and '{type_name(b)}'")


def _is_seq(a):
    return type(a) in (str, list, tuple)


def _seq_repeat(seq, n):
    if not is_int_like(n):
        raise type_error(f"can't multiply sequence by non-int of type '{type_name(n)}'")
    count = int(n)
    if count > 1 << 31:
        raise ExprError("", "MemoryError")
    k = max(0, count)
    fits(len(seq) * k)
    return seq * k


def binary(op, a, b):
    """PyNumber_Add and its kin for FreeCAD's operand types; op is add, sub, mul, div, mod or pow."""
    if op == "mod" and type(a) is str:   # calc() formats a str on the left, whatever is on the right
        return percent_format(a, b)
    # Python asks the left operand's type first: a Quantity answers (or refuses), a Vector answers, and a number, str or list
    # has nothing for a Vector and leaves it to the Vector's own handler
    if isinstance(a, Quantity):
        return _quantity_op(op, a, b)
    if isinstance(a, Vector) or isinstance(b, Vector):
        return _vector_op(op, a, b)
    if isinstance(b, Quantity):
        return _quantity_op(op, a, b)
    ra, rb = is_real(a), is_real(b)
    if (ra or type(a) is complex) and (rb or type(b) is complex):
        if type(a) is complex or type(b) is complex:
            return _complex_op(op, a, b)
        both_int = is_int_like(a) and is_int_like(b)
        if both_int:
            x, y = int(a), int(b)
            if op == "add":
                return x + y
            if op == "sub":
                return x - y
            if op == "mul":
                return x * y
            if op == "div":
                return int_true_div(x, y)
            if op == "mod":
                return int_mod(x, y)
            return int_pow(x, y)
        x, y = real_to_float(a), real_to_float(b)
        if op == "add":
            return x + y
        if op == "sub":
            return x - y
        if op == "mul":
            return x * y
        if op == "div":
            if y == 0:
                raise ExprError("float division by zero", "ZeroDivisionError")
            return x / y
        if op == "mod":
            return float_mod(x, y)
        return float_pow(x, y)
    ta, tb = type(a), type(b)
    if op == "add":
        if ta is tb and ta in (str, list, tuple):
            fits(len(a) + len(b))
            return a + b
        if ta in (str, list, tuple):
            raise type_error(f'can only concatenate {ta.__name__} (not "{type_name(b)}") to {ta.__name__}')
    elif op == "mul":
        if _is_seq(a) and not _is_seq(b):
            return _seq_repeat(a, b)
        if _is_seq(b) and not _is_seq(a):
            return _seq_repeat(b, a)
        if _is_seq(a) and _is_seq(b):
            raise type_error(f"can't multiply sequence by non-int of type '{type_name(b)}'")
    raise type_error(f"unsupported operand type(s) for {_SYMBOL[op]}: '{type_name(a)}' and '{type_name(b)}'")


def _complex_op(op, a, b):
    if op == "mod":
        raise type_error(f"unsupported operand type(s) for %=: '{type_name(a)}' and '{type_name(b)}'")
    x, y = _to_c(a), _to_c(b)
    if op == "add":
        return complex(x.real + y.real, x.imag + y.imag)
    if op == "sub":
        return complex(x.real - y.real, x.imag - y.imag)
    if op == "mul":
        return complex(x.real * y.real - x.imag * y.imag, x.real * y.imag + x.imag * y.real)
    if op == "div":
        if y.real * y.real + y.imag * y.imag == 0:
            raise ExprError("division by zero", "ZeroDivisionError")
        abs_breal, abs_bimag = abs(y.real), abs(y.imag)
        if abs_breal >= abs_bimag:
            if abs_breal == 0:
                raise ExprError("division by zero", "ZeroDivisionError")
            ratio = y.imag / y.real
            dd = y.real + y.imag * ratio
            return complex(_fdiv(x.real + x.imag * ratio, dd), _fdiv(x.imag - x.real * ratio, dd))
        ratio = y.real / y.imag
        dd = y.real * ratio + y.imag
        return complex(_fdiv(x.real * ratio + x.imag, dd), _fdiv(x.imag * ratio - x.real, dd))
    return complex_pow(x, y)


def neg(a):
    """PyNumber_Negative."""
    t = type(a)
    if t is int or t is bool:
        return -int(a)
    if t is float or t is complex:
        return -a
    if isinstance(a, Quantity):
        return Quantity(a.value * -1, a.dims)
    if isinstance(a, Vector):
        return Vector(-a.x, -a.y, -a.z)
    raise type_error(f"bad operand type for unary -: '{type_name(a)}'")


def pos(a):
    """PyNumber_Positive."""
    t = type(a)
    if t is int or t is float or t is complex:
        return a
    if t is bool:
        return int(a)
    if isinstance(a, Quantity):
        return Quantity(a.value, a.dims)
    if isinstance(a, Vector):
        return Vector(a.x, a.y, a.z)
    raise type_error(f"bad operand type for unary +: '{type_name(a)}'")


# ─── Printing ───────────────────────────────────────────────────────────────────────────────────

def int_str(v):
    """str(int), without the digit limit of Python 3.11+ (FreeCAD's answers come from str() as well)."""
    try:
        return str(v)
    except ValueError:
        pass
    if v < 0:
        return "-" + int_str(-v)
    chunk = 10 ** 1000
    parts = []
    while v:
        v, r = divmod(v, chunk)
        parts.append(r)
    return str(parts[-1]) + "".join(str(p).rjust(1000, "0") for p in reversed(parts[:-1]))


def py_repr(a):
    """repr(obj), as FreeCAD's Python prints the values."""
    t = type(a)
    if t is int:
        return int_str(a)
    if t in (float, bool, str, complex) or a is None:
        return repr(a)
    if isinstance(a, Quantity):
        return repr(a.value) + ("" if is_dimless(a.dims) else " " + unit_string(a.dims))
    if t is list:
        return "[" + ", ".join(py_repr(x) for x in a) + "]"
    if t is tuple:
        return f"({py_repr(a[0])},)" if len(a) == 1 else "(" + ", ".join(py_repr(x) for x in a) + ")"
    if isinstance(a, Other):
        return a.str
    if isinstance(a, Vector):
        return f"Vector ({a.x!r}, {a.y!r}, {a.z!r})"
    return repr(a)


def py_str(a):
    """str(obj)."""
    return a if type(a) is str else py_repr(a)


# ─── "%" formatting of a str ────────────────────────────────────────────────────────────────────

def _int_to_index(a, spec):
    if is_int_like(a):
        return int(a)
    raise type_error(f"%{spec} format: an integer is required, not {type_name(a)}")


def _long_of(a, spec):
    if is_int_like(a):
        return int(a)
    v = a if type(a) is float else a.value if isinstance(a, Quantity) else None
    if v is None:
        raise type_error(f"%{spec} format: a real number is required, not {type_name(a)}")
    if math.isnan(v):
        raise ExprError("cannot convert float NaN to integer", "ValueError")
    if math.isinf(v):
        raise ExprError("cannot convert float infinity to integer", "OverflowError")
    return int(v)


def _float_arg(a):
    if type(a) is float:
        return a
    if is_int_like(a):
        return float_of_int(int(a))
    if isinstance(a, Quantity):
        return a.value
    raise type_error(f"must be real number, not {type_name(a)}")


def _gen_format(v, prec, alt, upper):
    if not alt:
        s = to_number(v, "Default", prec)
    else:   # "#": the point stays and so do the trailing zeros
        s = "%#.*g" % (prec, v)
    return s.upper() if upper else s


def percent_format(fmt, arg):
    """PyUnicode_Format: the right operand is the one value, or the items of a tuple."""
    args = list(arg) if type(arg) is tuple else [arg]
    ai = 0

    def nxt():
        nonlocal ai
        if ai >= len(args):
            raise type_error("not enough arguments for format string")
        ai += 1
        return args[ai - 1]
    out = []
    out_len = 0
    chars = fmt
    n = len(chars)
    i = 0

    def at(k):
        return chars[k] if k < n else ""
    while i < n:
        ch = chars[i]
        if ch != "%":
            j = chars.find("%", i)
            j = n if j < 0 else j
            out.append(chars[i:j])
            out_len += j - i
            i = j
            continue
        i += 1
        if at(i) == "(":
            if type(arg) is list:
                raise type_error("list indices must be integers or slices, not str")
            raise type_error("format requires a mapping")
        minus = plus = space = alt = zero = False
        while i < n:
            f = chars[i]
            if f == "-":
                minus = True
            elif f == "+":
                plus = True
            elif f == " ":
                space = True
            elif f == "#":
                alt = True
            elif f == "0":
                zero = True
            else:
                break
            i += 1
        width, prec = -1, -1
        if at(i) == "*":
            w = nxt()
            if not is_int_like(w):
                raise type_error("* wants int")
            if not -9223372036854775808 <= int(w) <= 9223372036854775807:
                raise overflow("Python int too large to convert to C ssize_t")
            width = int(w)
            if width < 0:
                minus = True
                width = -width
            i += 1
        else:
            j = i
            while i < n and "0" <= chars[i] <= "9":
                i += 1
            if i > j:
                width = int(chars[j:i])
        if at(i) == ".":
            i += 1
            if at(i) == "*":
                p = nxt()
                if not is_int_like(p):
                    raise type_error("* wants int")
                if not -2147483648 <= int(p) <= 2147483647:
                    raise overflow("Python int too large to convert to C int")
                prec = max(0, int(p))
                i += 1
            else:
                j = i
                while i < n and "0" <= chars[i] <= "9":
                    i += 1
                prec = int(chars[j:i]) if i > j else 0
        if i < n and chars[i] in "hlL":
            i += 1
        if i >= n:
            raise ExprError("incomplete format", "ValueError")
        conv = chars[i]
        i += 1
        if conv == "%" and not (minus or plus or space or alt or zero or width >= 0 or prec >= 0):
            out.append("%")
            out_len += 1
            continue
        a = nxt()
        fits(width)
        fits(prec)
        sign, numeric, prefix = "", True, ""
        if conv in "sra":
            numeric = False
            body = py_str(a) if conv == "s" else py_repr(a)
            if conv == "a":
                body = body.encode("ascii", "backslashreplace").decode("ascii")
            if prec >= 0:
                body = body[:prec]
        elif conv == "c":
            numeric = False
            if is_int_like(a):
                v = int(a)
                if v < 0 or v > 0x10FFFF:
                    raise ExprError("%c arg not in range(0x110000)", "OverflowError")
                body = chr(v)
            elif type(a) is str and len(a) == 1:
                body = a
            else:
                raise type_error("%c requires int or char")
        elif conv in "diu":
            v = _long_of(a, conv)
            sign = "-" if v < 0 else "+" if plus else " " if space else ""
            body = int_str(abs(v))
            if prec >= 0:
                body = body.rjust(prec, "0")
        elif conv in "xXo":
            v = _int_to_index(a, conv)
            sign = "-" if v < 0 else "+" if plus else " " if space else ""
            body = format(abs(v), "o" if conv == "o" else conv)
            if prec >= 0:
                body = body.rjust(prec, "0")
            if alt:
                prefix = "0o" if conv == "o" else "0x" if conv == "x" else "0X"
        elif conv in "eEfFgG":
            v = _float_arg(a)
            p = 6 if prec < 0 else prec
            if not math.isfinite(v):
                body = "nan" if math.isnan(v) else "inf"
                sign = "-" if v < 0 else "+" if plus else " " if space else ""
                if conv in "EFG":
                    body = body.upper()
                zero = False
            else:
                negative = v < 0 or (v == 0 and math.copysign(1, v) < 0)
                sign = "-" if negative else "+" if plus else " " if space else ""
                av = abs(v)
                if conv in "eE":
                    body = ("%#.*e" if alt else "%.*e") % (p, av)
                    body = body.upper() if conv == "E" else body
                elif conv in "fF":
                    body = ("%#.*f" if alt else "%.*f") % (p, av)
                else:
                    body = _gen_format(av, p if p else 1, alt, conv == "G")
        else:
            c = ord(conv)
            raise ExprError(f"unsupported format character '{conv if 31 <= c <= 126 else '?'}' ({hex(c)}) at index {i - 1}", "ValueError")
        text = sign + prefix + body
        if width > len(text):
            if minus:
                text = text.ljust(width)
            elif zero and numeric:
                text = sign + prefix + body.rjust(width - len(sign) - len(prefix), "0")
            else:
                text = text.rjust(width)
        fits(out_len + len(text))
        out.append(text)
        out_len += len(text)
    # a list or a Vector is a mapping to PyUnicode_Format, which then does not mind arguments left over
    if ai < len(args) and type(arg) is not list and not isinstance(arg, Vector):
        raise type_error("not all arguments converted during string formatting")
    return "".join(out)


# ─── Components: a[i], a[i:j:k], a.name ─────────────────────────────────────────────────────────

def _index_of(i, what, length):
    if not is_int_like(i):
        raise type_error(f"{what} indices must be integers{'' if what == 'string' else ' or slices'}, not '{type_name(i)}'")
    k = int(i)
    if k < 0:
        k += length
    if k < 0 or k >= length:
        raise ExprError(f"{what} index out of range", "IndexError")
    return k


def get_item(obj, index):
    """PyObject_GetItem on a str, list or tuple; what Py::Sequence does to anything else."""
    t = type(obj)
    if t is str:
        return obj[_index_of(index, "string", len(obj))]
    if t is list:
        return obj[_index_of(index, "list", len(obj))]
    if t is tuple:
        return obj[_index_of(index, "tuple", len(obj))]
    raise type_error(f"PyCXX: Error creating object of type N2Py7SeqBaseINS_6ObjectEEE from {py_repr(obj)}")


def get_slice(obj, lo, hi, step):
    """A slice object applied (PySlice_New + PyObject_GetItem). Each bound is None or an int."""
    def bound(b):
        if b is None:
            return None
        if not is_int_like(b):
            raise type_error("slice indices must be integers or None or have an __index__ method")
        return int(b)
    if type(obj) not in (str, list, tuple):
        raise type_error(f"PyCXX: Error creating object of type N2Py7SeqBaseINS_6ObjectEEE from {py_repr(obj)}")
    s = bound(step)
    if s == 0:
        raise ExprError("slice step cannot be zero", "ValueError")
    return obj[slice(bound(lo), bound(hi), s)]


def get_attr(obj, name):
    """Attribute access on a value: what a number, a Quantity or a str offers here."""
    def no_attr():
        return ExprError(f"No attribute named '{name}'", "AttributeError")
    if isinstance(obj, Quantity):
        if name == "Value":
            return obj.value
        if name == "Unit":
            return Other("Unit", unit_object_string(obj.dims))
        if name == "UserString":
            return user_string(obj)[0]
        raise no_attr()
    t = type(obj)
    if t is int or t is bool:
        if name in ("real", "numerator"):
            return int(obj)
        if name == "imag":
            return 0
        if name == "denominator":
            return 1
        raise no_attr()
    if t is float:
        if name == "real":
            return obj
        if name == "imag":
            return 0.0
        raise no_attr()
    if t is complex:
        if name == "real":
            return obj.real
        if name == "imag":
            return obj.imag
        raise no_attr()
    raise no_attr()


def unit_object_string(dims):
    """Unit::representation(): "Unit: mm (1,0,0,0,0,0,0,0) [Length]"."""
    t = type_string(dims)
    return f"Unit: {unit_string(dims)} ({','.join(str(d) for d in dims)})" + (f" [{t}]" if t else "")


_install_operators()
