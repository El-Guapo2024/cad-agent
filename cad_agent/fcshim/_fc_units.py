# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses FreeCAD's Base::Unit and Base::Quantity and keeps FreeCAD's licence, the GNU
# Lesser General Public License, version 2.1 or (at your option) any later version; the text is in ../../ui/LICENSE.
#
#   Derived from: src/Base/Quantity.cpp, QuantityPyImp.cpp, Unit.cpp, UnitPyImp.cpp, UnitsSchemasData.h
#                 (Copyright (c) 2013 Juergen Riegel), FreeCAD (https://github.com/FreeCAD/FreeCAD),
#                 commit 3160daf1e2b62b0472854da4848255c6b3ad554c
#
# See ../../NOTICE.
"""FreeCAD.Units for the CAM workbench's Python: Unit (the eight exponents of Unit.cpp, in its order: Length, Mass,
Time, ElectricCurrent, ThermodynamicTemperature, AmountOfSubstance, LuminousIntensity, Angle), Quantity (a value in
internal units, mm, kg, s, rad shown as degrees ...), Quantity("5 mm") parsing the unit expressions CAM writes, and the
user strings of the Standard schema (UnitsSchemasData.h's "Internal")."""
from __future__ import annotations

import math
import re

_DIMS = ("Length", "Mass", "TimeSpan", "ElectricCurrent", "ThermodynamicTemperature", "AmountOfSubstance",
         "LuminousIntensity", "Angle")


class Unit:
    __slots__ = ("sig",)

    def __init__(self, *args):
        if all(isinstance(a, int) for a in args):
            vals = [int(a) for a in args] + [0] * (8 - len(args))
            self.sig = tuple(vals[:8])
        elif len(args) == 1 and isinstance(args[0], Unit):
            self.sig = args[0].sig
        elif len(args) == 1 and isinstance(args[0], Quantity):
            self.sig = args[0].Unit.sig
        elif len(args) == 1 and isinstance(args[0], str):
            self.sig = Quantity.parse(args[0]).Unit.sig
        else:
            vals = [int(a) for a in args] + [0] * (8 - len(args))
            self.sig = tuple(vals[:8])

    def __eq__(self, o):
        return isinstance(o, Unit) and self.sig == o.sig

    def __hash__(self):
        return hash(self.sig)

    def __mul__(self, o):
        return Unit(*[a + b for a, b in zip(self.sig, o.sig)])

    def __truediv__(self, o):
        return Unit(*[a - b for a, b in zip(self.sig, o.sig)])

    def pow(self, n):
        return Unit(*[a * n for a in self.sig])

    @property
    def Signature(self):
        return self.sig

    @property
    def Type(self):
        return TYPE_NAMES.get(self.sig, "")

    def isEmpty(self):
        return not any(self.sig)

    def __repr__(self):
        return f"Unit: {self.getString()} ({','.join(str(s) for s in self.sig)}) [{self.Type}]"

    def getString(self):
        names = ("mm", "kg", "s", "A", "K", "mol", "cd", "deg")
        num = [(n, e) for n, e in zip(names, self.sig) if e > 0]
        den = [(n, -e) for n, e in zip(names, self.sig) if e < 0]

        def part(lst):
            return "*".join(n if e == 1 else f"{n}^{e}" for n, e in lst)
        if not num and not den:
            return ""
        s = part(num) if num else "1"
        if den:
            d = part(den)
            s += "/" + (f"({d})" if len(den) > 1 else d)
        return s


def _u(*sig):
    return Unit(*sig)


LENGTH = _u(1)
MASS = _u(0, 1)
TIME = _u(0, 0, 1)
ANGLE = _u(0, 0, 0, 0, 0, 0, 0, 1)
TYPE_NAMES = {(1, 0, 0, 0, 0, 0, 0, 0): "Length", (2, 0, 0, 0, 0, 0, 0, 0): "Area", (3, 0, 0, 0, 0, 0, 0, 0): "Volume",
              (0, 1, 0, 0, 0, 0, 0, 0): "Mass", (0, 0, 1, 0, 0, 0, 0, 0): "TimeSpan",
              (0, 0, 0, 0, 0, 0, 0, 1): "Angle", (1, 0, -1, 0, 0, 0, 0, 0): "Velocity",
              (1, 0, -2, 0, 0, 0, 0, 0): "Acceleration", (0, 0, -1, 0, 0, 0, 0, 0): "Frequency",
              (0, 0, 0, 0, 0, 0, 0, 0): ""}

# unit tokens (Quantity.l's), as (factor to internal units, signature)
_UNITS = {
    "nm": (1e-6, LENGTH), "um": (1e-3, LENGTH), "µm": (1e-3, LENGTH), "mm": (1.0, LENGTH), "cm": (10.0, LENGTH),
    "dm": (100.0, LENGTH), "m": (1e3, LENGTH), "km": (1e6, LENGTH), "in": (25.4, LENGTH), '"': (25.4, LENGTH),
    "ft": (304.8, LENGTH), "'": (304.8, LENGTH), "thou": (0.0254, LENGTH), "mil": (0.0254, LENGTH),
    "yd": (914.4, LENGTH), "mi": (1609344.0, LENGTH),
    "s": (1.0, TIME), "ms": (1e-3, TIME), "min": (60.0, TIME), "h": (3600.0, TIME),
    "g": (1e-3, MASS), "kg": (1.0, MASS), "mg": (1e-6, MASS), "t": (1e3, MASS), "lb": (0.45359237, MASS),
    "deg": (1.0, ANGLE), "°": (1.0, ANGLE), "rad": (180.0 / math.pi, ANGLE), "gon": (360.0 / 400.0, ANGLE),
    "Hz": (1.0, _u(0, 0, -1)), "kHz": (1e3, _u(0, 0, -1)),
    "ml": (1e3, _u(3)), "l": (1e6, _u(3)),
}
_UNIT_TOKEN = re.compile("(" + "|".join(re.escape(k) for k in sorted(_UNITS, key=len, reverse=True)) + ")")


class Quantity:
    __slots__ = ("_value", "_unit", "Format")

    def __init__(self, *args):
        self.Format = {"Precision": 2, "NumberFormat": "g", "Denominator": 8}
        self._unit = Unit()
        self._value = 0.0
        if not args:
            return
        a = args[0]
        if len(args) == 1:
            if isinstance(a, Quantity):
                self._value, self._unit = a._value, a._unit
            elif isinstance(a, str):
                q = Quantity.parse(a)
                self._value, self._unit = q._value, q._unit
            elif isinstance(a, Unit):
                self._value, self._unit = 1.0, a
            else:
                self._value = float(a)
            return
        if len(args) == 2:
            v, u = args
            self._value = float(v)
            if isinstance(u, Unit):
                self._unit = u
            elif isinstance(u, Quantity):
                self._unit = u._unit
            elif isinstance(u, str):
                q = Quantity.parse("1 " + u)
                self._value = float(v) * q._value
                self._unit = q._unit
            return
        self._value = float(a)
        self._unit = Unit(*args[1:])

    # ── parsing (the unit expressions FreeCAD's Quantity grammar takes, without its full arithmetic) ──
    @staticmethod
    def parse(text: str) -> "Quantity":
        s = text.strip()
        m = re.match(r"^([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)\s*(.*)$", s)
        if not m:
            raise ValueError(f"Quantity::parse: syntax error in {text!r}")
        value = float(m.group(1))
        rest = m.group(2).strip()
        if not rest:
            return Quantity(value)
        factor, unit = _parse_unit(rest, text)
        q = Quantity()
        q._value, q._unit = value * factor, unit
        return q

    @property
    def Value(self):
        return self._value

    @Value.setter
    def Value(self, v):
        self._value = float(v)

    @property
    def Unit(self):
        return self._unit

    @Unit.setter
    def Unit(self, u):
        self._unit = u

    def getValueAs(self, *args):
        a = args[0]
        if isinstance(a, Quantity):
            q = a
        elif isinstance(a, Unit):
            q = Quantity(1.0, a)
        elif isinstance(a, str):
            q = Quantity.parse("1 " + a) if not re.match(r"^\s*[-+\d.]", a) else Quantity.parse(a)
        else:
            q = Quantity(float(a))
        if not q._unit.isEmpty() and q._unit != self._unit:
            raise ValueError(f"Unit mismatch (`{q._unit.getString()}` != `{self._unit.getString()}`)")
        return Quantity(self._value / q._value)

    def _schema(self):
        t = self._unit.Type
        v = abs(self._value)
        if t == "Length":
            for lim, name, f in ((1e-6, "mm", 1.0), (1e-3, "nm", 1e-6), (1e-1, "µm", 1e-3), (1e4, "mm", 1.0),
                                 (1e7, "m", 1e3), (1e10, "km", 1e6)):
                if v < lim:
                    return name, f
            return "m", 1e3
        if t == "Area":
            for lim, name, f in ((1e2, "mm^2", 1.0), (1e6, "cm^2", 1e2), (1e12, "m^2", 1e6)):
                if v < lim:
                    return name, f
            return "km^2", 1e12
        if t == "Volume":
            for lim, name, f in ((1e3, "mm^3", 1.0), (1e6, "ml", 1e3), (1e9, "l", 1e6)):
                if v < lim:
                    return name, f
            return "m^3", 1e9
        if t == "Angle":
            return "°", 1.0
        if t == "Velocity":
            return "mm/s", 1.0
        if t == "Acceleration":
            return "mm/s^2", 1.0
        if t == "TimeSpan":
            return "s", 1.0
        if t == "Mass":
            return "kg", 1.0
        return self._unit.getString(), 1.0

    def getUserPreferred(self):
        name, f = self._schema()
        return (self._fmt(name, f), f, name)

    def _fmt(self, name, f):
        prec = self.Format.get("Precision", 2)
        txt = f"{self._value / f:.{prec}f}"
        return f"{txt} {name}" if name else txt

    @property
    def UserString(self):
        return self.getUserPreferred()[0]

    def toStr(self, decimals=None):
        if decimals is None:
            return f"{self._value} {self._unit.getString()}".strip()
        return f"{self._value:.{decimals}f} {self._unit.getString()}".strip()

    # ── arithmetic (QuantityPy's number handlers) ──
    def _other(self, o):
        return o if isinstance(o, Quantity) else Quantity(float(o))

    def __add__(self, o):
        o = self._other(o)
        if o._unit != self._unit:
            raise ValueError("Quantity::operator +(): Unit mismatch in plus operation")
        return Quantity(self._value + o._value, self._unit)

    def __radd__(self, o):
        return self.__add__(o)

    def __sub__(self, o):
        o = self._other(o)
        if o._unit != self._unit:
            raise ValueError("Quantity::operator -(): Unit mismatch in minus operation")
        return Quantity(self._value - o._value, self._unit)

    def __rsub__(self, o):
        return self._other(o).__sub__(self)

    def __mul__(self, o):
        if isinstance(o, Quantity):
            return Quantity(self._value * o._value, self._unit * o._unit)
        if hasattr(o, "x") and hasattr(o, "y") and hasattr(o, "z"):     # a Vector
            return o * self._value
        return Quantity(self._value * float(o), self._unit)

    def __rmul__(self, o):
        return self.__mul__(o)

    def __truediv__(self, o):
        if isinstance(o, Quantity):
            return Quantity(self._value / o._value, self._unit / o._unit)
        return Quantity(self._value / float(o), self._unit)

    def __rtruediv__(self, o):
        return Quantity(float(o) / self._value, Unit() / self._unit)

    def __neg__(self):
        return Quantity(-self._value, self._unit)

    def __pos__(self):
        return Quantity(self)

    def __abs__(self):
        return Quantity(abs(self._value), self._unit)

    def __pow__(self, n):
        return Quantity(self._value ** float(n), self._unit.pow(int(n)))

    def __mod__(self, o):
        return Quantity(math.fmod(self._value, float(o)), self._unit)

    def __float__(self):
        return float(self._value)

    def __int__(self):
        return int(self._value)

    def __round__(self, n=None):
        return Quantity(round(self._value, n) if n is not None else round(self._value), self._unit)

    def __bool__(self):
        return self._value != 0.0

    def _cmp_val(self, o):
        if isinstance(o, Quantity):
            if o._unit != self._unit and not (self._unit.isEmpty() or o._unit.isEmpty()):
                raise ValueError("Quantity::operator <(): quantities need to have same unit to compare")
            return o._value
        return float(o)

    def __eq__(self, o):
        if isinstance(o, Quantity):
            return self._value == o._value and self._unit == o._unit
        if isinstance(o, (int, float)):
            return self._value == float(o)
        return NotImplemented

    def __ne__(self, o):
        r = self.__eq__(o)
        return r if r is NotImplemented else not r

    def __lt__(self, o):
        return self._value < self._cmp_val(o)

    def __le__(self, o):
        return self._value <= self._cmp_val(o)

    def __gt__(self, o):
        return self._value > self._cmp_val(o)

    def __ge__(self, o):
        return self._value >= self._cmp_val(o)

    __hash__ = None

    def __repr__(self):
        u = self._unit.getString()
        return f"{self._value} {u}" if u else f"{self._value}"

    __str__ = __repr__

    def __format__(self, spec):
        return format(self._value, spec)

    def __reduce__(self):
        return (_restore, (self._value, self._unit.sig))


def _restore(v, sig):
    return Quantity(v, Unit(*sig))


def _parse_unit(rest: str, text: str):
    """factor and Unit of a unit expression: tokens joined by '*', '/', '^n', and a parenthesised denominator."""
    s = rest.replace(" ", "")
    factor, unit = 1.0, Unit()
    sign = 1
    i = 0
    paren = False
    while i < len(s):
        c = s[i]
        if c == "*":
            i += 1
            continue
        if c == "/":
            sign = -1
            i += 1
            if i < len(s) and s[i] == "(":
                paren = True
                i += 1
            continue
        if c == ")":
            paren = False
            sign = 1
            i += 1
            continue
        m = _UNIT_TOKEN.match(s, i)
        if not m:
            raise ValueError(f"Quantity::parse: unknown unit in {text!r}")
        tok = m.group(1)
        i = m.end()
        exp = 1
        m2 = re.match(r"\^(-?\d+)", s[i:])
        if m2:
            exp = int(m2.group(1))
            i += m2.end()
        f, u = _UNITS[tok]
        e = exp * sign
        factor *= f ** e
        unit = unit * u.pow(e)
        if not paren:           # a/b*c is (a/b)*c: '/' takes the next factor only, or a parenthesised group
            sign = 1
    return factor, unit


# FreeCAD.Units' named units
Length = LENGTH
Mass = MASS
TimeSpan = TIME
Angle = ANGLE
Area = _u(2)
Volume = _u(3)
Velocity = _u(1, 0, -1)
Acceleration = _u(1, 0, -2)
Frequency = _u(0, 0, -1)
MilliMetre = Quantity(1.0, LENGTH)
Metre = Quantity(1e3, LENGTH)
Inch = Quantity(25.4, LENGTH)
Degree = Quantity(1.0, ANGLE)
Radian = Quantity(180.0 / math.pi, ANGLE)
Second = Quantity(1.0, TIME)
Minute = Quantity(60.0, TIME)


def parseQuantity(text):
    return Quantity.parse(text)


def toNumber(q, fmt="g", decimals=-1):
    v = q.Value if isinstance(q, Quantity) else float(q)
    return f"{v:.{decimals}{fmt}}" if decimals >= 0 else f"{v:{fmt}}"


def getSchema():
    return 0


def listSchemas(n=None):
    names = ["Standard (mm, kg, s, °)"]
    return names[n] if n is not None else tuple(names)


def schemaTranslate(q, schema=0):
    s, f, name = q.getUserPreferred()
    return (s, f, name)
