# SPDX-License-Identifier: LGPL-2.1-or-later
# Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
# LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
#   src/App/Expression.cpp: 2015 Eivind Kvedalen
#   src/Base/Tools.h: 2009 Werner Mayer
#   src/Base/Vector3D.cpp: 2005 Imetric 3D GmbH
"""FreeCAD's expression functions (FunctionExpression::evaluate in App/Expression.cpp, as ui/src/expr.ts has them) for
cad_agent/fcexpr.py: the aggregates and their collectors, the numeric functions, str, parsequant, address, list and tuple, and the
vector functions with the checks that come before a matrix, a placement or a rotation (which this engine does not build)."""
import math

from . import fcexpr_py as P
from .fcexpr import Range, _in_expr, _property_value, column_name, evaluate
from .fcexpr_py import ExprError, Vector, py_repr, py_str
from .fcexpr_quantity import (ANGLE, EPSILON, LENGTH, ZERO, Quantity, QuantityError, c_acos, c_asin, c_atan, c_cbrt, c_ceil,
                              c_cos, c_cosh, c_exp, c_floor, c_fmod, c_log, c_sin, c_sinh, c_sqrt, c_tan, c_tanh, cpow,
                              parse_quantity)


# ─── Functions (FunctionExpression::evaluate) ──────────────────────────────────────────────────────

_AGGREGATES = frozenset(("sum", "average", "stddev", "count", "min", "max", "and", "or"))
_AGGREGATE_KINDS = frozenset(("quantity", "float", "int"))


def _as_bool(v):
    return abs(v) >= 1e-7


class _Collector:
    """The collectors of the aggregate functions (Collector and its subclasses in Expression.cpp)."""

    def __init__(self, f):
        self.f = f
        self.q = Quantity(0.0, ZERO)
        self.first = True
        self.n = 0
        self.mean = Quantity(0.0, ZERO)
        self.m2 = Quantity(0.0, ZERO)

    def collect(self, v):
        f = self.f
        if f not in ("and", "or") and self.first:
            self.q = Quantity(self.q.value, v.dims)
        if f == "sum":
            self.q = P.q_add_assign(self.q, v)
        elif f == "average":
            self.q = P.q_add_assign(self.q, v)
            self.n += 1
        elif f == "count":
            self.n += 1
        elif f == "min":
            if self.first or P.q_less(v, self.q):
                self.q = v
        elif f == "max":
            if self.first or P.q_greater(v, self.q):
                self.q = v
        elif f == "and":
            if self.first:
                self.q = Quantity(1.0 if _as_bool(v.value) else 0.0, ZERO)
            elif not _as_bool(v.value):
                self.q = Quantity(0.0, ZERO)
        elif f == "or":
            if self.first:
                self.q = Quantity(1.0 if _as_bool(v.value) else 0.0, ZERO)
            elif _as_bool(v.value):
                self.q = Quantity(1.0, ZERO)
        elif f == "stddev":
            if self.first:
                self.m2 = Quantity(0.0, P.unit_mul(v.dims, v.dims))
                self.mean = Quantity(0.0, v.dims)
                self.n = 0
            delta = P.q_sub(v, self.mean)
            self.n += 1
            self.mean = P.q_add(self.mean, P.q_div(delta, Quantity(float(self.n), ZERO)))
            self.m2 = P.q_add(self.m2, P.q_mul(delta, P.q_sub(v, self.mean)))
        self.first = False

    def result(self):
        if self.f == "average":
            return P.q_div(self.q, Quantity(float(self.n), ZERO))
        if self.f == "count":
            return Quantity(float(self.n), ZERO)
        if self.f == "stddev":
            if self.n < 2:
                raise ExprError("Invalid number of entries: at least two required.", "ExpressionError")
            return Quantity(P.q_pow_q(P.q_div(self.m2, Quantity(float(self.n - 1), ZERO)), Quantity(0.5, ZERO)).value, self.mean.dims)
        return self.q


def _boost_round(v, name):
    """boost::math::round and trunc: neither takes a value that is not finite."""
    if not math.isfinite(v):
        what = "nan" if math.isnan(v) else "inf" if v > 0 else "-inf"
        raise ExprError(f"Error in function boost::math::{name}<double>(double): Value {what} can not be represented in the target integer type.", "FreeCADError")
    if name == "trunc":
        return c_floor(v) if v >= 0 else c_ceil(v)
    if -0.5 < v < 0.5:
        return 0.0
    if v > 0:
        c = float(math.ceil(v))
        return c - 1 if c - v > 0.5 else c
    fl = float(math.floor(v))
    return fl + 1 if v - fl > 0.5 else fl


_PI = math.pi


def _to_radians(d):
    return d * (_PI / 180)


def _angle_or_none(q):
    return P.is_dimless(q.dims) or q.dims == ANGLE


def _int_of(v):
    return int(v)


def _fail(n, cls, msg):
    raise ExprError(_in_expr(msg, n), cls)


_NUMERIC = {"acos": c_acos, "asin": c_asin, "atan": c_atan, "abs": abs, "exp": c_exp, "log": c_log,
            "log10": lambda v: c_log(v) / math.log(10), "sin": c_sin, "sinh": c_sinh, "tan": c_tan, "tanh": c_tanh, "sqrt": c_sqrt,
            "cbrt": c_cbrt, "cos": c_cos, "cosh": c_cosh, "ceil": c_ceil, "floor": c_floor,
            "round": lambda v: _boost_round(v, "round"), "trunc": lambda v: _boost_round(v, "trunc"),
            "not": lambda v: 0.0 if _as_bool(v) else 1.0}
_OBJECT_FUNCTIONS = frozenset("""create matrix placement rotation vector translationm minvert mrotate mrotatex mrotatey mrotatez mscale
mtranslate rotationx rotationy rotationz vangle vcross vdot vlinedist vlinesegdist vlineproj vnormalize vplanedist vplaneproj vscale
vscalex vscaley vscalez""".split())


def _aggregate_quantity(n, value, kind):
    if kind is not None and kind not in _AGGREGATE_KINDS:
        raise ExprError(_in_expr("Invalid property type for aggregate.", n), "ExpressionError")
    q = P.to_quantity(_property_value(value))
    if q is None:
        raise ExprError(_in_expr("Invalid property type for aggregate.", n), "ExpressionError")
    return q


def eval_function(n, env):
    f, args = n.f, n.args
    if f in _AGGREGATES:
        c = _Collector(f)
        for a in args:
            if type(a) is Range:
                for _, value, kind in env.cells(a):
                    c.collect(_aggregate_quantity(n, value, kind))
            else:
                q = P.to_quantity(evaluate(a, env))
                if q is not None:
                    c.collect(q)
        return P.from_quantity(c.result())
    if f in ("list", "tuple"):
        if len(args) == 1 and type(args[0]) is Range:
            lv = evaluate(args[0], env)
            if f == "list":
                return lv
            _fail(n, "TypeError", f"PyCXX: Error creating object of type N2Py5TupleE from {py_repr(lv)}")
        items = [evaluate(a, env) for a in args]
        return items if f == "list" else tuple(items)
    if not args:
        _fail(n, "ExpressionError", "Function requires at least one argument.")
    if f == "str":
        return py_str(evaluate(args[0], env))
    if f == "parsequant":
        text = py_str(evaluate(args[0], env))
        try:
            return parse_quantity(text)
        except ExprError:
            raise
        except QuantityError as e:
            etype = "ArithmeticError" if e.kind == "mismatch" else "ParserError" if e.kind == "syntax" else "ArithmeticError"
            raise ExprError(e.message, etype, e.kind) from None
    if f in ("hiddenref", "href"):
        return evaluate(args[0], env)
    if f == "address":
        row, col = evaluate(args[0], env), evaluate(args[1], env)
        if not P.is_int_like(row):
            _fail(n, "ExpressionError", "Function requires the first argument to be an integer.")
        if not P.is_int_like(col):
            _fail(n, "ExpressionError", "Function requires the second argument to be an integer.")
        abs_row = abs_col = True
        if len(args) > 2:
            ref = evaluate(args[2], env)
            if not P.is_int_like(ref):
                _fail(n, "ExpressionError", "Function requires the third argument to be an integer.")
            value = int(ref)
            if value < 1 or value > 4:
                _fail(n, "ExpressionError", "Invalid reference type: must be 1, 2, 3, or 4.")
            abs_row = value in (1, 2)
            abs_col = value in (1, 3)
        r, cc = int(row), int(col)
        if r < 1 or r > 16384 or cc < 1 or cc > 702:
            _fail(n, "ExpressionError", "Cell address out of bounds.")
        return f"{'$' if abs_col else ''}{column_name(cc)}{'$' if abs_row else ''}{r}"
    if f in _OBJECT_FUNCTIONS:
        return _eval_object_function(n, env)

    # the numeric functions: every argument is made a quantity first, in order
    def arg(i, msg):
        q = P.to_quantity(evaluate(args[i], env))
        if q is None:
            _fail(n, "TypeError", msg)
        return q
    v1 = arg(0, "Invalid first argument.")
    v2 = arg(1, "Invalid second argument.") if len(args) > 1 else None
    v3 = arg(2, "Invalid third argument.") if len(args) > 2 else None
    value = v1.value
    dims = ZERO
    scaler = 1.0
    if f in ("cos", "sin", "tan"):
        if not _angle_or_none(v1):
            _fail(n, "ExpressionError", "Unit must be either empty or an angle.")
        value = _to_radians(value)
    elif f in ("acos", "asin", "atan"):
        if not P.is_dimless(v1.dims):
            _fail(n, "ExpressionError", "Unit must be empty.")
        dims = ANGLE
        scaler = 180 / _PI
    elif f in ("exp", "log", "log10", "sinh", "tanh", "cosh"):
        if not P.is_dimless(v1.dims):
            _fail(n, "ExpressionError", "Unit must be empty.")
    elif f in ("round", "trunc", "ceil", "floor", "abs"):
        dims = v1.dims
    elif f == "sqrt":
        dims = P.unit_root(v1.dims, 2)
    elif f == "cbrt":
        dims = P.unit_root(v1.dims, 3)
    elif f == "atan2":
        if v1.dims != v2.dims:
            _fail(n, "ExpressionError", "Units must be equal.")
        dims = ANGLE
        scaler = 180 / _PI
    elif f == "mod":
        if v1.dims != v2.dims and not P.is_dimless(v1.dims) and not P.is_dimless(v2.dims):
            _fail(n, "ExpressionError", "Units must be equal or dimensionless.")
        dims = v1.dims
    elif f == "pow":
        if not P.is_dimless(v2.dims):
            _fail(n, "ExpressionError", "Exponent is not allowed to have a unit.")
        exponent = v2.value
        if not P.is_dimless(v1.dims):
            if exponent - _boost_round(exponent, "round") < 1e-9:
                dims = P.unit_pow(v1.dims, exponent)
            else:
                _fail(n, "ExpressionError", "Exponent must be an integer when used with a unit.")
    elif f in ("hypot", "cath"):
        if v1.dims != v2.dims:
            _fail(n, "ExpressionError", "Units must be equal.")
        if len(args) > 2 and v2.dims != v3.dims:
            _fail(n, "ExpressionError", "Units must be equal.")
        dims = v1.dims
    elif f != "not":
        _fail(n, "ExpressionError", f"Unknown function: {f}")
    if f == "mod":
        output = c_fmod(value, v2.value)
    elif f == "atan2":
        output = math.atan2(value, v2.value)
    elif f == "pow":
        output = cpow(value, v2.value)
    elif f == "hypot":
        output = c_sqrt(cpow(v1.value, 2) + cpow(v2.value, 2) + (cpow(v3.value, 2) if v3 else 0))
    elif f == "cath":
        output = c_sqrt(cpow(v1.value, 2) - cpow(v2.value, 2) - (cpow(v3.value, 2) if v3 else 0))
    else:
        fn = _NUMERIC.get(f)
        if fn is None:
            _fail(n, "ExpressionError", f"Unknown function: {f}")
        output = fn(value)
    return Quantity(scaler * output, dims)


# ─── Vectors, and the checks that come before a matrix, a placement or a rotation ─────────────────────────────

_NEEDS_GEOMETRY = "Function requires the first argument to be either Matrix, Placement or Rotation."


def _not_built(n):
    """What the engine does not build: a Matrix, a Placement or a Rotation (exprdiff excuses the cases where FreeCAD makes one)."""
    return ExprError(_in_expr("This evaluator does not build a Matrix, a Placement or a Rotation.", n), "NotImplementedError")


def _float_or_inf(v):
    try:
        return float(v)
    except OverflowError:
        return math.inf if v > 0 else -math.inf


def _as_double(v):
    """PyArg_ParseTuple's "d": a number Python can turn into a float, else None."""
    if type(v) is float:
        return v
    if P.is_int_like(v):
        try:
            return float(int(v))
        except OverflowError:
            return None
    if isinstance(v, Quantity):
        return v.value
    return None


def _vector_from_args(args):
    """VectorPy::PyInit: three floats (fewer are zeros), a Vector, or a list or tuple of three floats; None where Python raises."""
    if len(args) <= 3:
        d = [_as_double(a) for a in args]
        if all(x is not None for x in d):
            d += [0.0] * (3 - len(d))
            return d
    if len(args) == 1:
        a = args[0]
        if isinstance(a, Vector):
            return list(a.v)
        if type(a) in (list, tuple):
            d = [x if type(x) is float else _float_or_inf(x) if type(x) is int else None for x in a]
            if len(d) == 3 and all(x is not None for x in d):
                return d
    return None


def _vector_arg(n, i, env):
    a = evaluate(n.args[i], env)
    if not isinstance(a, Vector):
        raise ExprError(_in_expr("Argument must be a vector.", n), "ExpressionError")
    return a.v


def _length_arg(n, i, env):
    q = P.to_quantity(evaluate(n.args[i], env))
    if q is None:
        raise ExprError(_in_expr("Failed to convert to Quantity.", n), "TypeError")
    if not P.is_dimless(q.dims) and q.dims != LENGTH:
        raise ExprError(_in_expr("Unit must be either empty or a length.", n), "ExpressionError")
    return q.value


def _to_degrees(r):
    return r * (180 / _PI)


def _sequence_items(v):
    """The items of a sequence Python can iterate (a str, a list, a tuple or a Vector), else None."""
    if type(v) is str:
        return list(v)
    if type(v) in (list, tuple):
        return list(v)
    if isinstance(v, Vector):
        return list(v.v)
    return None


def _vector_init(args):
    v = _vector_from_args(args)
    if v is None:
        raise P.system_error()   # the constructor failed and the call went on with its exception set
    return Vector(*v)


_fdiv = P._fdiv


def _eval_object_function(n, env):
    f, args = n.f, n.args
    if f == "vector":
        return _vector_init([evaluate(a, env) for a in args])
    if f == "create":
        typ = evaluate(args[0], env)
        if type(typ) is not str:
            _fail(n, "ExpressionError", "Function requires the first argument to be a string.")
        name = typ.lower()
        if name not in ("matrix", "vector", "placement", "rotation"):
            _fail(n, "ExpressionError", f"Unknown type '{typ}'.")
        rest = [evaluate(a, env) for a in args[1:]]
        if name != "vector":
            raise _not_built(n)
        return _vector_init(rest) if rest else Vector(0.0, 0.0, 0.0)
    if f in ("matrix", "placement", "rotation"):
        for a in args:
            evaluate(a, env)
        raise _not_built(n)
    if f == "minvert":
        evaluate(args[0], env)
        _fail(n, "ExpressionError", _NEEDS_GEOMETRY)
    if f == "mrotate":
        for a in args[1:]:
            evaluate(a, env)
        evaluate(args[0], env)
        _fail(n, "ExpressionError", _NEEDS_GEOMETRY)
    if f in ("mrotatex", "mrotatey", "mrotatez"):
        q = P.to_quantity(evaluate(args[1], env))
        if q is None:
            _fail(n, "TypeError", "Invalid rotation angle.")
        if not _angle_or_none(q):
            _fail(n, "ExpressionError", "Unit must be either empty or an angle.")
        evaluate(args[0], env)
        _fail(n, "ExpressionError", _NEEDS_GEOMETRY)
    if f in ("mscale", "mtranslate"):
        if len(args) == 2:
            second = evaluate(args[1], env)
            items = _sequence_items(second)
            if items is None:
                _fail(n, "ExpressionError", f"Second parameter is not a sequence type: '{py_str(second)}'.")
            if len(items) != 3:
                _fail(n, "ExpressionError", f"Second parameter provided has {len(items)} elements instead of 3.")
            values = items
        else:
            values = [evaluate(args[1], env), evaluate(args[2], env), evaluate(args[3], env)]
        if not all(_as_double(x) is not None for x in values):
            _fail(n, "ExpressionError", "Error parsing scale values.")
        evaluate(args[0], env)
        _fail(n, "ExpressionError", _NEEDS_GEOMETRY)
    if f == "translationm":
        if len(args) == 1:
            p = evaluate(args[0], env)
            items = _sequence_items(p)
            if items is None:
                _fail(n, "ExpressionError", f"Not sequence type: '{py_str(p)}'.")
            if len(items) != 3:
                _fail(n, "ExpressionError", f"Sequence provided has {len(items)} elements instead of 3.")
            if not all(_as_double(x) is not None for x in items):
                _fail(n, "ExpressionError", "Error parsing sequence.")
            raise _not_built(n)
        qs = []
        for i, a in enumerate(args):
            q = P.to_quantity(evaluate(a, env))
            if q is None:
                _fail(n, "TypeError", f"Invalid {('first', 'second', 'third')[i]} argument.")
            qs.append(q)
        if not all(P.is_dimless(q.dims) or q.dims == LENGTH for q in qs):
            _fail(n, "ExpressionError", "Translation units must be a length or dimensionless.")
        raise _not_built(n)
    if f in ("rotationx", "rotationy", "rotationz"):
        q = P.to_quantity(evaluate(args[0], env))
        if q is None:
            _fail(n, "TypeError", "Invalid first argument.")
        if not _angle_or_none(q):
            _fail(n, "ExpressionError", "Unit must be either empty or an angle.")
        raise _not_built(n)
    # the vector functions: each argument is taken as it is needed
    v1 = _vector_arg(n, 0, env)
    if f == "vnormalize":
        ln = P.vec_length(v1)
        return Vector(*((v1[0] / ln, v1[1] / ln, v1[2] / ln) if ln != 0 and ln != 1 else v1))
    if f == "vscale":
        return Vector(v1[0] * _length_arg(n, 1, env), v1[1] * _length_arg(n, 2, env), v1[2] * _length_arg(n, 3, env))
    if f == "vscalex":
        return Vector(v1[0] * _length_arg(n, 1, env), v1[1], v1[2])
    if f == "vscaley":
        return Vector(v1[0], v1[1] * _length_arg(n, 1, env), v1[2])
    if f == "vscalez":
        return Vector(v1[0], v1[1], v1[2] * _length_arg(n, 1, env))
    v2 = _vector_arg(n, 1, env)
    if f == "vangle":
        len1, len2 = P.vec_length(v1), P.vec_length(v2)
        if len1 <= EPSILON or len2 <= EPSILON:
            angle = math.nan
        else:
            dot = P.vec_dot(v1, v2)
            dot /= len1
            dot /= len2
            angle = _PI if dot <= -1 else 0.0 if dot >= 1 else math.acos(dot)
        return Quantity(_to_degrees(angle), ANGLE)
    if f == "vcross":
        return Vector(*P.vec_cross(v1, v2))
    if f == "vdot":
        return P.vec_dot(v1, v2)
    v3 = _vector_arg(n, 2, env)
    if f == "vlinedist":
        return Quantity(abs(_fdiv(P.vec_length(P.vec_cross(v3, P.vec_sub(v1, v2))), P.vec_length(v3))), LENGTH)
    if f == "vlinesegdist":   # DistanceToLineSegment(p1 = v2, p2 = v3)
        len2 = P.vec_sqr(P.vec_sub(v2, v3))
        if len2 == 0:
            return Vector(*v2)
        p2p1, pxp1 = P.vec_sub(v3, v2), P.vec_sub(v1, v2)
        q = P.vec_dot(pxp1, p2p1) / len2
        t = 0 if q < 0 else 1 if 1 < q else q
        return Vector(*P.vec_sub(P.vec_scale(p2p1, t), pxp1))
    if f == "vlineproj":   # ProjectToLine(point = v2, line = v3)
        k = _fdiv(P.vec_dot(v2, v3), P.vec_sqr(v3))
        return Vector(*P.vec_sub(P.vec_scale(v3, k), v2))
    if f == "vplanedist":
        return Quantity(_fdiv(P.vec_dot(P.vec_sub(v1, v2), v3), P.vec_length(v3)), LENGTH)
    if f == "vplaneproj":   # ProjectToPlane(base = v2, normal = v3)
        k = _fdiv(P.vec_dot(P.vec_sub(v1, v2), v3), P.vec_sqr(v3))
        return Vector(*P.vec_sub(v1, P.vec_scale(v3, k)))
    _fail(n, "ExpressionError", f"Unknown function: {f}")
