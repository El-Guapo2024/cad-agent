# SPDX-License-Identifier: LGPL-2.1-or-later
"""The expression cases of scripts/exprdiff.py: what FreeCAD's expression language accepts, and what it refuses.

Derived from FreeCAD main 3160daf1e2b6 (the commit PARITY.md ports): the lexer (src/App/Expression.l: every
unit token, the number rules, the constants, the function-call rule, the string rule), the grammar
(src/App/Expression.y: each production, each precedence level, the unit_exp / us_building_unit forms),
FunctionExpression (src/App/Expression.cpp: every function and its argument rules, the aggregate collectors),
OperatorExpression::calc (the Python number protocol each operator runs through) and FreeCAD's own tests
(tests/src/App/ExpressionParser.cpp, Expression.cpp, src/Mod/Spreadsheet/TestSpreadsheet.py,
src/Mod/Test/Document.py).

    cases() -> [(category, text), ...]   deterministic, de-duplicated, in a stable order

The names an expression may use (ENV) are properties of the owning object in FreeCAD; scripts/exprdiff_fc.py
creates them there and scripts/exprdiff-entry.ts gives the same values to our evaluator.
"""
import itertools
import os
import random

# EXPRDIFF_SEED=N draws other random cases (the default, 0, is the set whose FreeCAD answers scripts/exprdiff/fc_answers.json.gz stores).
SEED = int(os.environ.get("EXPRDIFF_SEED", "0"))

# Every UNIT / USUNIT token of src/App/Expression.l (132: Quantity.l has the same ones).
UNITS = ["nm", "um", "µm", "mm", "cm", "dm", "m", "km", "l", "ml", "Hz", "kHz", "MHz", "GHz", "THz", "ug", "µg", "mg",
         "g", "kg", "t", "s", "min", "h", "A", "nA", "uA", "µA", "mA", "kA", "MA", "K", "mK", "µK", "uK", "mol", "nmol",
         "µmol", "umol", "mmol", "cd", "in", "\"", "ft", "'", "thou", "mil", "yd", "mi", "mph", "sqft", "cft", "lb", "lbm",
         "oz", "st", "cwt", "lbf", "N", "mN", "kN", "MN", "Pa", "kPa", "MPa", "GPa", "bar", "mbar", "Torr", "mTorr", "uTorr",
         "µTorr", "psi", "ksi", "Mpsi", "W", "nW", "uW", "µW", "mW", "kW", "VA", "V", "kV", "mV", "MS", "kS", "S", "mS",
         "uS", "µS", "Ohm", "kOhm", "MOhm", "C", "T", "mT", "G", "Wb", "F", "mF", "µF", "uF", "nF", "pF", "H", "mH", "µH",
         "uH", "nH", "J", "mJ", "kJ", "Nm", "Nmm", "VAs", "CV", "Ws", "kWh", "eV", "keV", "MeV", "cal", "kcal", "°", "deg",
         "rad", "gon", "M", "′", "AS", "″"]
# One unit of each kind of quantity, for the pairings.
REPS = ["mm", "in", "kg", "lb", "s", "min", "A", "K", "mol", "cd", "deg", "rad", "N", "Pa", "W", "V", "Ohm", "Hz", "l", "psi"]
FUNCS1 = ["abs", "acos", "asin", "atan", "cbrt", "ceil", "cos", "cosh", "exp", "floor", "log", "log10", "round", "sin", "sinh",
          "sqrt", "tan", "tanh", "trunc", "not", "str", "parsequant", "hiddenref", "href"]
FUNCS2 = ["atan2", "mod", "pow", "hypot", "cath"]
AGG = ["sum", "average", "count", "max", "min", "stddev", "and", "or"]
ALL_FUNCS = ["abs", "acos", "asin", "atan", "atan2", "cath", "cbrt", "ceil", "cos", "cosh", "exp", "floor", "hypot", "log",
             "log10", "mod", "pow", "round", "sin", "sinh", "sqrt", "tan", "tanh", "trunc", "vangle", "vcross", "vdot",
             "vlinedist", "vlinesegdist", "vlineproj", "vnormalize", "vplanedist", "vplaneproj", "vscale", "vscalex",
             "vscaley", "vscalez", "minvert", "mrotate", "mrotatex", "mrotatey", "mrotatez", "mscale", "mtranslate",
             "create", "list", "matrix", "placement", "rotation", "rotationx", "rotationy", "rotationz", "str", "parsequant",
             "translationm", "tuple", "vector", "address", "hiddenref", "href", "not", "average", "count", "max", "min",
             "stddev", "sum", "and", "or"]
# What the owner object has: (property type, name, value). scripts/exprdiff_fc.py makes these properties in FreeCAD, the answers
# file records them, and scripts/exprdiff-entry.ts gives its evaluator the same values.
PROPERTIES = [("App::PropertyLength", "pLen", "10 mm"), ("App::PropertyLength", "pWid", "20 mm"),
              ("App::PropertyAngle", "pAng", "30 deg"), ("App::PropertyMass", "pMass", "2 kg"),
              ("App::PropertyInteger", "pCnt", 3), ("App::PropertyFloat", "pRat", 0.5),
              ("App::PropertyString", "pStr", "abc"), ("App::PropertyBool", "pOn", True),
              ("App::PropertyString", "pLong", "abcdefghij"), ("App::PropertyStringList", "pList", ["a", "b", "c", "d", "e", "f"])]
NAMES = [name for _, name, _ in PROPERTIES]
OWNER = "Obj"      # the object's name, in the document DOC
DOC = "T"
BINOPS = ["+", "-", "*", "/", "%", "^", "==", "!=", "<", ">", "<=", ">="]


def _uniq(items):
    seen, out = set(), []
    for cat, text in items:
        if text not in seen:
            seen.add(text)
            out.append((cat, text))
    return out


def numbers():
    out = ["0", "1", "2", "3", "7", "10", "12", "100", "1000", "12345", "65536", "2147483647", "2147483648", "4294967296",
           "9223372036854775806", "9223372036854775807", "9223372036854775808", "99999999999999999999",
           "0.5", ".5", "5.", "0.", ".", "00012", "007", "1.50", "3.14159265358979", "2.718281828459045", "1.5.3", "1..2",
           "1.2.3.4", "1e3", "1E3", "1e+3", "1e-3", "1.5e3", "1.5E-3", ".5e1", "5.e1", "1e", "1e+", "1e-", "1e3.5", "1e3e3",
           "2e", "2E", "1e308", "1.7976931348623157e308", "1e309", "1e-307", "1e-320", "1e-323", "1e-400", "4.9e-324",
           "123456789012345678901234567890", "0.1", "0.2", "0.30000000000000004", "1,5", "1,5,5", ",5", "5,", "1,5e3", "1,5e-3",
           "1,", "1,,5", "1 000", "1_000", "0x10", "0b1", "0o7", "1d3", "1f", "1L", "+1", "-1", "+-1", "-+1", "--1", "++1",
           "- 1", "+ 1", "-0", "-0.0", "0.0", "0e0", "1e0", "1e1", "10e-1", "1000000", "1e6", "1e10", "1e15", "1e16", "1e20",
           "3000000000", "-3000000000", "2147483647.5", "-2147483648", "-2147483649", "4.0", "4.5", "-4.5", "1.000000000001",
           "0.1 + 0.2", "0.1 * 3", "1 / 3", "2 / 3", "10 / 4", "10 / 5", "1e-9", "1e-7", "1e-6", "123.456", "0.000001",
           "1.0e3", "1.0E3", "٣", "１", "²", "1²",
           "0." + "0" * 38 + "1", "0." + "0" * 37 + "1", "1" + "0" * 38 + ".5", "1" + "0" * 37 + ".5", "1" * 39 + "e1", "1" * 40 + "e1", "1" * 38 + ",5", "1" * 39 + ",5",
           "0.5" + "0" * 40, "00000000000000000000000000000000000000000000000000.5", "1e-3" + "0" * 40]
    return [("num", t) for t in out]


def literals_with_units():
    out = []
    for u in UNITS:
        sp = " " if u[0].isalpha() or u[0] in "µ" else ""
        out += [f"1 {u}", f"{u}", f"2.5 {u}", f"-3 {u}", f"1{u}", f"1.5{u}", f"1 {u}^2", f"1 {u}^-1", f"1 {u}^3",
                f"(1) {u}", f"(1 + 1) {u}", f"1/{u}", f"1 / 2 {u}", f"1 {u} + 1 {u}", f"3 {u} * 2", f"2 * 3 {u}", f"1 {u} / 1 {u}",
                f"(1 {u})^2", f"1e3 {u}", f"0 {u}", f"1 {u} == 1 {u}", f"1 {u}*{u}", f"1 {u}/{u}"]
    return [("unit", t) for t in out]


def unit_pairs():
    out = []
    for a, b in itertools.product(REPS, REPS):
        out += [f"1 {a} + 1 {b}", f"2 {a} - 1 {b}", f"2 {a} * 3 {b}", f"2 {a} / 4 {b}", f"1 {a} == 1 {b}", f"1 {a} < 2 {b}",
                f"1 {a}/{b}", f"1 {a}*{b}"]
    # unit expressions in the unit_exp grammar
    for a, b in itertools.product(["mm", "m", "kg", "s", "N", "A", "deg"], ["mm", "s", "kg", "m", "A"]):
        out += [f"1 {a}/{b}", f"1 {a}/{b}^2", f"1 {a}^2/{b}", f"1 {a}/({b})", f"1/{a}/{b}", f"1 ({a}*{b})", f"1 {a}/({b}*{b})",
                f"2 {a}/{b}^2*3", f"(2 {a})/{b}", f"2 {a}*3 {b}", f"1 {a}^2*{b}", f"{a}/{b}", f"{a}*{b}", f"{a}^2", f"({a})"]
    return [("unit2", t) for t in out]


def unit_powers():
    out = []
    for u in ["mm", "s", "kg", "A", "K", "deg", "m/s", "N", "J", "Pa", "Hz", "mm/s^2"]:
        for n in [-10, -9, -8, -7, -3, -2, -1, 0, 1, 2, 3, 4, 7, 8, 9, 10]:
            out += [f"1 {u}^{n}", f"2 ({u})^{n}" if "/" in u else f"2 {u}^{n}", f"(2 {u})^{n}", f"pow(2 {u}; {n})",
                    f"(2 {u})^{n}.0", f"(3 {u})^({n}/1)"]
        for x in [0.5, 1.5, 2.5, -0.5, 1e-9, 0.9999999999, 1.0000000001, 2.0000000001]:
            out += [f"(4 {u})^{x}", f"pow(4 {u}; {x})"]
    for u in ["mm^2", "mm^3", "mm^4", "mm^6", "mm^8", "mm^-2", "mm^-4", "s^2", "kg^2", "m^2/s^2"]:
        out += [f"sqrt(4 {u})", f"cbrt(8 {u})", f"sqrt(-4 {u})", f"abs(-3 {u})", f"(4 {u})^0.5", f"(8 {u})^(1/3)"]
    return [("upow", t) for t in out]


def building_units():
    out = ["5' 3\"", "5'3\"", "5' 3.5\"", "5.5' 3\"", "5\" 3'", "5' 3 in", "5 ft 3 in", "5ft 3in", "5' 3", "5' 3'", "5\" 3\"",
           "5' 3\" 2'", "1' + 1\"", "1' - 1\"", "(5' 3\") * 2", "2 * 5' 3\"", "5' 3\" + 1 in", "5' 3\" == 63 in", "-5' 3\"",
           "5'", "5\"", "5' 3\" 1\"", "1/2\"", "1/2'", "(1/2)\"", "1 1/2\"", "3' 1/2\"", "5 ' 3 \"", "5 '3 \"", "5'-3\"",
           "5' -3\"", "5' +3\"", "5'+3\"", "-5' -3\"", "1\" mm", "1 mm \"", "1\"^2", "1'^2", "1\"/s", "1'/s", "1\" * 2",
           "2 * 1\"", "1' 1\" 1'", "0' 0\"", "5' 12\"", "1e1' 1e1\"", "1' 1e1\"", "1,5' 1,5\"", ".5' .5\""]
    return [("building", t) for t in out]


def operators():
    out = []
    triples = [(2, 3, 4), (12, 3, 2), (2, 3, 2), (7, 2, 3)]
    for o1, o2 in itertools.product(BINOPS, BINOPS):
        for a, b, c in triples:
            out += [f"{a} {o1} {b} {o2} {c}", f"({a} {o1} {b}) {o2} {c}", f"{a} {o1} ({b} {o2} {c})"]
        out += [f"{triples[0][0]}{o1}{triples[0][1]}{o2}{triples[0][2]}", f"2 mm {o1} 3 mm {o2} 4 mm",
                f"2 {o1} 3 mm {o2} 4", f"2.5 {o1} 3.5 {o2} 4.5"]
    for o in BINOPS:
        out += [f"2 {o} 3", f"2 {o} -3", f"-2 {o} 3", f"2 {o} +3", f"2 {o} 0", f"0 {o} 2", f"0 {o} 0", f"2.5 {o} 0.5", f"-2.5 {o} 0.5",
                f"2 mm {o} 3 mm", f"2 mm {o} 3", f"2 {o} 3 mm", f"2 mm {o} 3 s", f"2 {o} <<a>>", f"<<a>> {o} 2", f"<<a>> {o} <<b>>",
                f"True {o} 2", f"2 {o} True", f"None {o} 2", f"2 {o} None", f"pLen {o} 2", f"2 {o} pLen", f"pLen {o} pWid",
                f"pCnt {o} pCnt", f"pRat {o} pCnt", f"pStr {o} pStr", f"pOn {o} pOn", f"pAng {o} 2", f"1 {o} {o} 1", f"{o} 1", f"1 {o}",
                f"(1) {o} (2)", f"1 {o} 2 {o} 3 {o} 4"]
    # unary signs
    for u in ["-", "+", "--", "-+", "+-", "++", "- -", "+ +", "-(-", "---", "-1+"]:
        for ctx in ["{u}2", "{u}2^2", "2^{u}2", "2*{u}2", "{u}2*3", "{u}2 mm", "3-{u}2", "2^{u}2^2", "({u}2) mm", "{u}2 mm^2", "{u}pLen",
                    "2 {u}2", "{u}(2)", "{u}2 + 3", "{u}2 == {u}2", "{u}sin(30)", "{u}pi", "{u}True", "{u}None", "{u}<<a>>", "{u}mm",
                    "1 {u} 2", "{u}2 ? 1 : 2", "1 ? {u}2 : 3", "2^{u}1", "2^-{u}1"]:
            out.append(ctx.replace("{u}", u))
    return [("op", t) for t in out]


def conditionals():
    conds = ["0", "1", "2", "-1", "0.5", "1e-8", "1e-9", "0.0000001", "True", "False", "None", "<<>>", "<<a>>", "<<0>>", "0 mm", "1 mm",
             "1e-8 mm", "pOn", "pStr", "pCnt", "pRat", "pLen", "1 == 1", "1 == 2", "1 < 2", "2 < 1", "1 mm < 1 s", "sin(0)", "sin(30)",
             "not(0)", "not(1)", "and(1;0)", "or(1;0)", "pi", "e", "round(0.4)", "mod(4;2)", "list(0)", "tuple(0;0)", "1/0", "0/1",
             "0.0", "-0.0", "1 mm - 1 mm", "1 - 1", "True - 1", "False + 1"]
    outs = ["1", "2", "1 mm", "2 mm", "<<yes>>", "<<no>>", "pLen", "None", "True", "1/0", "sin(30)"]
    out = []
    for c in conds:
        out += [f"{c} ? 1 : 2", f"({c}) ? 1 : 2", f"{c} ? 1 mm : 2 mm", f"{c} ? 1 : 2 mm", f"{c} ? <<yes>> : <<no>>", f"{c} ? 1/0 : 2",
                f"{c} ? 2 : 1/0", f"1 + ({c} ? 1 : 2)", f"{c} ? 1 : 2 + 3", f"({c} ? 1 : 2) + 3", f"{c} ? {c} ? 1 : 2 : 3",
                f"{c} ? 1 : {c} ? 2 : 3", f"{c} ?1:2", f"{c}?1:2"]
    for a, b in itertools.product(outs, outs):
        out += [f"1 ? {a} : {b}", f"0 ? {a} : {b}"]
    out += ["1 ? 2", "1 ? : 2", "? 1 : 2", "1 ? 2 : ", "1 : 2", "1 ? 2 ? 3 : 4 : 5", "1 ? 2 : 3 ? 4 : 5", "0 ? 2 : 3 ? 4 : 5",
            "1 ? 2 : 3 : 4", "1 == 1 ? 2 : 3", "1 + 1 == 2 ? 3 : 4", "1 ? 2 : 3 == 3", "1 ? 2 : 3 + 4", "(1 ? 2 : 3) ? 4 : 5",
            "1 ? (2 ? 3 : 4) : 5", "1 ? 2 : (3 ? 4 : 5)", "1 ? 2 mm : 3 s", "0 ? 2 mm : 3 s", "1 ? sin(1;2) : 3", "0 ? 1 : sin(1;2)",
            "1 mm < 1 ? 1 : 2", "1 < 1 mm ? 1 : 2"]
    return [("cond", t) for t in out]


def functions():
    args1 = ["0", "1", "-1", "0.5", "-0.5", "2", "2.5", "-2.5", "3.5", "10", "30", "45", "60", "90", "180", "270", "360", "720",
             "1e-9", "1e9", "100", "pi", "e", "pi/2", "1/3", "-1/3", "True", "False", "None", "<<abc>>", "<<12>>", "<<1 mm>>",
             "1 mm", "-1 mm", "4 mm^2", "8 mm^3", "9 mm^2", "2 mm^2", "1 kg", "1 s", "30 deg", "1 rad", "90 deg", "0.5 rad", "1 gon",
             "1 M", "1 AS", "1 deg + 1 rad", "1 N", "pLen", "pAng", "pCnt", "pRat", "pStr", "pOn", "pMass", "pLen * pLen",
             "pLen / pLen", "sin(30)", "1 mm / 1 mm", "2 mm / 1 mm", "1/0", "0.1 + 0.2", "1e3", "123456.789", "1 mm / 3"]
    out = []
    for f in sorted(set(FUNCS1)):
        for a in args1:
            out.append(f"{f}({a})")
        out += [f"{f}()", f"{f}(1;2)", f"{f}(1; 2; 3)", f"{f}(1,5)", f"{f}( 1 )", f"{f} (1)", f"{f}\t(1)", f"{f}(", f"{f})", f"{f}(1", f"{f}", f"{f}(,)",
                f"{f}(1,)", f"{f}(;1)", f"{f}((1))", f"{f}(-1)", f"{f}(+1)", f"2*{f}(1)", f"{f}(1)^2", f"-{f}(1)", f"{f}({f}(1))", f"{f}(1)(2)",
                f"{f}(1) mm", f"{f}(1) == {f}(1)", f"{f}(1) ? 1 : 2", f"1 {f}(1)", f"1 + {f}(1) mm", f"{f}(1)[0]", f"{f}(1).x",
                f"{f}(1) {f}(1)", f"{f}(A1:A2)"]
    twos = ["0", "1", "2", "-1", "0.5", "2.5", "10", "1 mm", "2 mm", "-2 mm", "1 s", "30 deg", "pLen", "pCnt", "pRat", "pStr", "True", "None", "<<a>>",
            "sin(30)", "4 mm^2", "1 mm / 1 s"]
    for f in FUNCS2:
        for a, b in itertools.product(twos, twos):
            out.append(f"{f}({a}; {b})")
        out += [f"{f}(1;2;3)", f"{f}(1;2;3;4)", f"{f}(1)", f"{f}(1, 2)", f"{f}(1,2)", f"{f}(1 , 2)", f"{f}(1 mm, 2 mm)", f"{f}(1 mm;2 mm;3 mm)"]
    for f in AGG:
        for n in range(1, 5):
            step = {1: 1, 2: 1, 3: 11, 4: 97}[n]
            for combo in itertools.islice(itertools.product(["1", "2.5", "3 mm", "-1 mm", "4 s", "<<a>>", "pLen", "pCnt", "True", "None", "30 deg", "0"], repeat=n), 0, None, step):
                out.append(f"{f}({'; '.join(combo)})")
        out += [f"{f}(1;2;3;4)", f"{f}(1;2;3;4;5;6)", f"{f}(1 mm;2 mm)", f"{f}(A1:A3)", f"{f}(1;A1:A3)", f"{f}(A1:A3;1)", f"{f}(A1:B2)", f"{f}(Z1:Z9)",
                f"{f}(pLen;pWid)", f"{f}(pLen;pLen;pLen)", f"{f}(pCnt;pRat)", f"{f}(pStr;1)", f"{f}(pOn;pOn)", f"{f}(1,2)", f"{f}(1, 2)", f"{f}(1;2)",
                f"{f}(sin(30);cos(60))", f"{f}(1/3;2/3;1)", f"{f}(0.1;0.2;0.3)", f"{f}(1e-8;1)", f"{f}(10 mm;1 cm;0.1 m)", f"{f}(1 mm;1 deg)"]
    # the spreadsheet tests' aggregate examples
    for f in AGG:
        out += [f"{f}(1)", f"{f}(1;2)", f"{f}(1;2;3)", f"{f}(0)", f"{f}(0;1;2)", f"{f}(0;1;2;3)", f"{f}(4mm;5mm;6mm)", f"{f}(4mm;5mm;6mm;6)"]
    # the functions by name, in every argument count
    for f in ALL_FUNCS:
        for n in range(0, 6):
            out.append(f"{f}({'; '.join(['1'] * n)})")
            if n >= 1:
                out.append(f"{f}({'; '.join(['1 mm'] * n)})")
    out += ["pow(2 mm, 3)", "sum(1 mm, 2 mm, 3 mm)", "atan2(1 mm, 1 mm)", "sqrt(9 mm^2)", "sqrt(1, 2)", "sqrt", "sqrt()", "list(1 mm, 2 mm)[0]",
            "<<(Line 1\\nLine 2)>>", "parsequant(<<(1 + 2) m>>)", "parsequant(str(1 m + 2 mm))", "parsequant(1 mm)", "parsequant()",
            "parsequant(<<10 deg>>)", "parsequant(<<(10 + 20) kg>>)", "parsequant(str(10 kg + 20010 g))", "parsequant(<<abc>>)", "parsequant(<<>>)",
            "parsequant(1)", "parsequant(pLen)", "parsequant(<<1e3 mm>>)", "parsequant(<<1 mm + 1 kg>>)", "parsequant(<<[x] 1 mm>>)",
            "Sin(30)", "SIN(30)", "sin (30)", "sin(30)", "sin(30 deg)", "sin(30 °)", "sin(pi/6 rad)", "cos(pi rad)", "tan(45)", "tan(90)",
            "tan(45 deg)", "asin(0.5)", "acos(0.5)", "atan(1)", "atan2(1; 1)", "atan2(-1; -1)", "atan2(0; 0)", "atan2(1 mm; 1 mm)",
            "atan2(1 mm; 1 s)", "atan2(1 mm; 1)", "sinh(1)", "cosh(1)", "tanh(1)", "exp(1)", "log(e)", "log10(100)", "log10(1000)",
            "log(0)", "log(-1)", "log10(0)", "log10(-1)", "sqrt(-1)", "sqrt(2)", "cbrt(-8)", "cbrt(27)", "cbrt(2)", "abs(-3)", "abs(-3 mm)",
            "round(2.5)", "round(-2.5)", "round(0.5)", "round(-0.5)", "round(1.4999999999999999)", "round(2.675)", "trunc(-2.5)", "trunc(2.5)",
            "ceil(-2.5)", "ceil(2.1)", "floor(-2.5)", "floor(2.9)", "round(2.5 mm)", "mod(7; 3)", "mod(-7; 3)", "mod(7; -3)", "mod(7.5; 2)",
            "mod(7 mm; 3 mm)", "mod(7 mm; 3)", "mod(7; 3 mm)", "mod(7 mm; 3 s)", "mod(5; 0)", "mod(5.5; 0)", "pow(2; 10)", "pow(2; -1)",
            "pow(2; 0.5)", "pow(-8; 1/3)", "pow(0; -1)", "pow(2 mm; 2)", "pow(2 mm; 0.5)", "pow(2 mm; 2 mm)", "pow(2; 2 mm)", "hypot(3; 4)",
            "hypot(3 mm; 4 mm)", "hypot(3 mm; 4 s)", "hypot(1; 2; 2)", "hypot(1 mm; 2 mm; 2 mm)", "cath(5; 3)", "cath(5 mm; 3 mm)", "cath(3; 5)",
            "cath(5; 3; 4)", "cath(9; 4; 4)", "hypot(3;4;5;6)", "hypot(0;0)", "hypot(1e200; 1e200)", "hypot(1e300; 1e300)"]
    return [("fn", t) for t in out]


def constants():
    out = []
    for c in ["pi", "e", "True", "true", "False", "false", "None", "none", "NONE", "TRUE", "FALSE", "PI", "Pi", "E", "Pi()", "pi()", "e()",
              "pi mm", "e mm", "True mm", "False mm", "None mm", "pi * 2", "2 pi", "2 e", "pi pi", "pi^2", "e^2", "e^pi", "pi^e", "-pi", "+pi", "pi/2",
              "pi rad", "(pi) rad", "180 / pi", "sin(pi)", "cos(pi)", "sin(pi rad)", "cos(pi rad)", "e1", "e1e", "pi2", "pie", "pi.x", "e.x", "True.x",
              "2e", "2 e3", "e3", "e-3", "e+3", "1e3e", "True + True", "True * True", "True / True", "True - True", "True ^ 2", "True % 2",
              "True == 1", "True == True", "True != False", "True < 2", "False < True", "False == 0", "False == None", "None == None",
              "None != None", "None < 1", "None == 0", "not(True)", "not(False)", "not(None)", "and(True;False)", "or(True;False)",
              "True ? 1 : 2", "False ? 1 : 2", "None ? 1 : 2", "-True", "-False", "-None", "+None", "+True", "str(True)", "str(False)", "str(None)",
              "str(pi)", "str(e)", "True and False", "pi == 3.141592653589793", "e == 2.718281828459045", "pi - 3.141592653589793",
              "round(pi; 2)", "True mm + 1 mm", "True s", "1 True", "True 1", "pi e", "e pi", "pi + e", "pi * e"]:
        out.append(c)
    return [("const", t) for t in out]


def strings():
    out = ["<<abc>>", "<<>>", "<< >>", "<<a b>>", "<<a>> <<b>>", "<<a\\nb>>", "<<a\\tb>>", "<<a\\rb>>", "<<a\\\\b>>", "<<a\\'b>>", "<<a\\\"b>>",
           "<<a\\xb>>", "<<a\\>>", "<<a\\>>>", "<<a>b>>", "<<a>>b>>", "<<a<<b>>", "<<<<a>>", "<<<a>>", "<<a>>>", "<<a>", "<<a", "<a>>", "<<a>> >>",
           "<<é>>", "<<日本語>>", "<<😀>>", "<<a\nb>>", "<<a\tb>>", "<<1 + 2>>", "<<(12,345.67 mm)>>", "<<12,34,567", "<<%d>>", "<<%s>> % 5",
           "<<%d items>> % 5", "<<%5.2f>> % 3.14159", "<<%x>> % 255", "<<%o>> % 8", "<<%e>> % 12345.678", "<<%g>> % 0.00001234", "<<%c>> % 65",
           "<<%s and %s>> % tuple(1; 2)", "<<%s>> % <<x>>", "<<%r>> % <<x>>", "<<%%>> % 0", "<<%s>> % 1.5", "<<%d>> % 1.5", "<<%d>> % <<a>>",
           "<<%s %s>> % 1", "<<%s>> % pLen", "<<%s>> % pCnt", "<<%s>> % pStr", "<<%i>> % 3", "<<%u>> % 3", "<<%X>> % 255", "<<%5d|>> % 42",
           "<<%-5d|>> % 42", "<<%05d>> % 42", "<<%+d>> % 42", "<<% d>> % 42", "<<%.3s>> % <<abcdef>>", "<<%10s|>> % <<ab>>", "<<%-10s|>> % <<ab>>",
           "<<a>> + <<b>>", "<<a>> + 1", "1 + <<a>>", "<<a>> - <<b>>", "<<a>> * 3", "3 * <<a>>", "<<a>> * 0", "<<a>> * -1", "<<a>> * 2.5",
           "<<a>> * 2.0", "<<a>> * (4/2)", "<<a>> * True", "<<a>> * pCnt", "<<a>> * pRat", "<<a>> * 1 mm", "<<a>> / 2", "<<a>> ^ 2", "<<a>> % 2",
           "<<a>> == <<a>>", "<<a>> != <<a>>", "<<a>> == <<b>>", "<<a>> < <<b>>", "<<b>> < <<a>>", "<<a>> <= <<a>>", "<<a>> >= <<b>>", "<<A>> < <<a>>",
           "<<a>> < <<ab>>", "<<é>> < <<z>>", "<<😀>> < <<￿>>", "<<a>> == 1", "<<1>> == 1", "<<a>> < 1", "1 < <<a>>", "<<a>> == pStr", "pStr == <<abc>>",
           "pStr + <<d>>", "pStr * 2", "str(pStr)", "str(<<a>>)", "str(1)", "str(1.5)", "str(1/3)", "str(2/2)", "str(1e20)", "str(1e-5)", "str(1e-4)",
           "str(0.0001)", "str(123456789.123)", "str(1 mm)", "str(1.5 mm)", "str(1/3 mm)", "str(-0.0)", "str(pLen)", "str(pAng)", "str(pCnt)",
           "str(pRat)", "str(pOn)", "str(1 mm/s^2)", "str(1 + 2)", "str(1 == 1)", "str(sin(30))", "str(list(1;2))", "str(tuple(1;2))", "str(sin(30) mm)",
           "str(1/0)", "str(10^20)", "str(2^100)", "str(2^-2)", "str(1e300*1e10)", "str(1 kg)", "str(1 deg)", "str(1 in)", "str(pi)", "str(e)",
           "str(100000000000000000000.5)", "str(0.1+0.2)", "str(1e16)", "str(1e15)", "str(12345678901234567)", "str(5 % 3)", "str(5.5 % 3)",
           "str(<<a>> + <<b>>)", "str(1; 2)", "str()", "str(str(1))", "str(str(<<a>>))", "str(-1 mm)", "str(0 mm)", "str(1e-9 mm)", "str(1e20 mm)",
           "str(1e22 mm)", "str(123456789012 mm)", "<<abc>>[1]", "<<abc>>.x", "pStr[1]", "pStr[0]", "pStr[-1]", "pStr[3]", "pStr[1:2]", "pStr[:2]",
           "pStr[1:]", "pStr[::2]", "pStr[::-1]", "pStr[0:3:2]", "pStr[:]", "pStr[1.5]", "pStr[<<a>>]", "pStr[pCnt]", "pStr[pCnt-1]", "pStr[pCnt-2]",
           "pStr.x", "pStr.real", "pStr[0][0]", "pStr[0:2][0]", "pStr[0:2].x", "<<a>> + str(2) + <<b>>", "str(1) + str(2)",
           "<<>> + <<>>", "<<a>> == <<a>> ? <<y>> : <<n>>", "<<a>> ? 1 : 2", "<<>> ? 1 : 2", "-<<a>>", "+<<a>>", "-<<>>", "<<a>> mm", "1 <<a>>",
           "<<a>> 1", "<<a>><<b>>", "<<a>> <<b>>", "<< a >>", "<<a  b>>", "<<\\>>", "<<\\\\>>", "<<\\\\\\>>", "<<\\n>>", "<<\\\\n>>",
           "<<a>>\n", "\n<<a>>", " <<a>> ", "\t<<a>>\t", "<<a>>\r", "<<abc>> .x", "<<a b c>>", "<<ab\\c>>", "<<tab\\there>>", "<<x\\ny>>",
           "tuple(<<a>>; <<b>>)", "list(<<a>>; <<b>>)", "list(<<a>>; 1)", "tuple(<<a>>; 1) + tuple(2)", "list(1) + list(2)", "list(1) * 2", "list(1;2) == list(1;2)",
           "list(1;2) != list(1;2)", "list(1;2) < list(1;3)", "list(1;2) < list(1)", "tuple(1;2) == tuple(1;2)", "tuple(1;2) < tuple(1;3)",
           "list(1;2) == tuple(1;2)", "list(1) + tuple(2)", "tuple(1) + list(2)", "tuple(1) + tuple(2)", "tuple(1) * 3", "3 * tuple(1)", "-list(1)",
           "list(1) ? 1 : 2", "tuple(0) ? 1 : 2", "list(list(1;2); 3)", "str(list(<<a>>; 1))", "str(tuple(<<a>>; 1.5; 1 mm))", "list(1 mm; 2 mm)",
           "list(1 mm; 2 mm) + list(3 mm)", "sum(list(1;2))", "max(list(1;2))", "count(list(1;2;3))", "list(A1:A3)", "tuple(A1:A3)", "list(A1:A3; 1)", "list(1; A1:A3)"]
    return [("str", t) for t in out]


def variables():
    out = []
    for n in NAMES + ["foo", "pLen2", "plen", "PLEN", "_x", "x_", "x1", "A1", "$A$1", "A$1", "$A1", "ab12", "AB123", "ABC1", "é", "éa", "aé", "a b", "a-b", "a.b",
                      "a.b.c", ".a", "..a", "a..b", "Obj", "Obj.pLen", "Obj.pCnt", "Obj.foo", "Obj.", ".pLen", ".pLen.x", "Obj.pLen.x",
                      "Placement", "Placement.Base.x", "Placement.Base", "Placement.Rotation.Angle", ".Placement.Base.x", "Obj.Placement.Base.y",
                      "<<Obj>>.pLen", "<<Obj>>.foo", "<<foo>>.pLen", "Doc#Obj.pLen", "<<T>>#Obj.pLen", "T#Obj.pLen", "T#Obj.foo", "T#Nope.pLen", "Nope#Obj.pLen",
                      "Obj.pLen.Value", "pLen.Value", "pLen.Unit", "pLen.UserString", "pCnt.real", "pRat.real",
                      "pLen[0]", "pCnt[0]", "pLen.x.y", "foo.bar", "foo[0]", "foo[0].x", "@x", "x@y", "x@", "#x", "x#", "x#y", "x#y.z", "m", "mm", "s", "t", "h",
                      "W", "x", "y", "z", "l", "dm", "e", "pi", "min", "max", "sum", "sin", "list", "tuple", "str", "vector", "A", "B", "Z99", "AA1", "AAA1", "A0",
                      "A1:A2", "A1:B2", "$A$1:$B$2", "a:b", "pLen:pWid", "A1:", ":A1", "A1:A2:A3"]:
        out.append(n)
    for n in NAMES:
        out += [f"{n} + 1", f"1 + {n}", f"{n} + 1 mm", f"{n} * 2", f"2 * {n}", f"{n} / 2", f"2 / {n}", f"{n} ^ 2", f"2 ^ {n}", f"{n} % 3", f"7 % {n}", f"-{n}", f"+{n}",
                f"{n} mm", f"2 {n}", f"{n} == {n}", f"{n} < {n}", f"{n} ? 1 : 2", f"sin({n})", f"sqrt({n})", f"abs({n})", f"round({n})", f"str({n})", f"({n})", f"{n}[0]",
                f"{n}.x", f"{n}()", f"{n}(1)", f"{n} {n}", f"{n}^{n}", f"{n}/{n}", f"{n}-{n}", f"{n}%{n}", f"min({n};1)", f"max({n};1 mm)", f"sum({n};{n})",
                f"hypot({n};{n})", f"atan2({n};{n})", f"pow({n};2)", f"pow(2;{n})", f"mod({n};2)", f"mod(7;{n})", f"True + {n}", f"{n} + True", f"{n} + <<a>>"]
    out += ["pLen + pWid", "pLen - pWid", "pLen * pWid", "pLen / pWid", "pLen ^ 2", "pLen % pWid", "pWid % pLen", "pLen == pWid", "pLen < pWid", "pLen + pAng",
            "pLen * pAng", "pAng + 1", "pAng + 1 deg", "sin(pAng)", "cos(pAng)", "tan(pAng)", "sin(pAng + 10)", "pAng * 2", "pAng / 2", "pAng / pAng", "pLen / pAng",
            "pMass * 9.81 m/s^2", "pMass * 9.81", "pLen * pLen * pLen", "(pLen * pWid) / pLen", "sqrt(pLen * pWid)", "pCnt * pLen", "pRat * pLen", "pLen * pRat",
            "pLen / pCnt", "pCnt / pLen", "pCnt ^ 2", "pCnt ^ -1", "pCnt ^ pRat", "pRat ^ pCnt", "pRat ^ pRat", "pCnt % 2", "pCnt % 0", "pRat % 0.3", "-pCnt % 2",
            "pCnt == 3", "pCnt == 3.0", "pRat == 0.5", "pLen == 10", "pLen == 10 mm", "pLen == 1 cm", "pLen < 1 cm", "pLen <= 1 cm", "pLen >= 1 cm", "pLen > 1 cm",
            "pLen != 1 cm", "pLen + 1 cm", "pLen - 1 cm", "pLen + pLen + pLen", "pLen > pAng", "pLen < pAng", "pLen == pAng", "pLen != pAng", "round(pLen / 3)",
            "floor(pLen / 3)", "ceil(pLen / 3)", "trunc(pLen / 3)", "pLen / 3", "mod(pLen; 3 mm)", "mod(pLen; 3)", "atan2(pLen; pWid)", "hypot(pLen; pWid)",
            "min(pLen; pWid)", "max(pLen; pWid)", "average(pLen; pWid)", "sum(pLen; pWid; 1 cm)", "stddev(pLen; pWid; pLen)", "count(pLen; pWid)", "pStr + pStr",
            "pStr * pCnt", "pStr == <<abc>>", "pStr != <<abc>>", "pStr < <<abd>>", "str(pCnt) + pStr", "pOn + 1", "pOn ? 1 : 2", "pOn == True", "pOn and 1", "not(pOn)",
            "and(pOn;1)", "or(pOn;0)", "pOn * pLen", "pOn + pLen"]
    return [("var", t) for t in out]


def python_semantics():
    nums = ["0", "1", "2", "-3", "0.5", "-1.5", "2.5", "10", "1e300", "True", "pCnt", "pRat", "1 mm", "-2 mm", "3 cm", "0 mm", "sin(30)", "sin(0)", "pLen", "None"]
    out = []
    for a, b in itertools.product(nums, nums):
        for o in ["+", "-", "*", "/", "%", "^", "==", "<", ">=", "!="]:
            out.append(f"({a}) {o} ({b})")
    # large and exact integers
    out += ["2^10", "2^31", "2^32", "2^62", "2^63", "2^64", "2^100", "2^200", "-2^63", "(-2)^63", "(-2)^64", "10^18", "10^19", "10^20", "10^30", "3^40", "7^7^7",
            "2^1000", "2^-1074", "2^-1075", "2^1023", "2^1024", "2.0^1024", "2^0.5", "(-2)^0.5", "(-8)^(1/3)", "(-1)^0.5", "(-1)^1.5", "0^0", "0^0.0", "0.0^0",
            "0^-1", "0^-1.0", "0.0^-1", "0^-0.5", "0^0.5", "1^1e300", "1^-1e300", "(-1)^1e300", "(-1)^1e301", "inf", "1e308*10", "1e308*10 - 1e308*10",
            "-1e308*10", "(1e308*10)/(1e308*10)", "1e308 + 1e308", "-(1e308 + 1e308)", "1e308 * 1e308", "2^3^2", "2^(3^2)", "(2^3)^2", "-2^2", "(-2)^2", "-(2^2)",
            "2^-2", "2^-2^2", "(1/3)^2", "1/3^2", "9^0.5", "9^(1/2)", "8^(1/3)", "27^(1/3)", "1e10", "1e10 + 1", "1e10 - 1e10", "1e10 mm", "1e10 * 1", "3000000000",
            "3000000000 mm", "3000000000 + 1", "3000000000.5", "3000000000.5 mm", "2147483647 + 1", "2147483647 mm", "2147483648 mm", "-2147483648 mm", "-2147483649 mm",
            "4294967296 mm", "10000000000 mm", "1e15 mm", "1e18 mm", "1e19 mm", "9007199254740993", "9007199254740993 mm", "123456789012345 mm", "0.5 + 0.5",
            "1/2 + 1/2", "2 * 0.5", "6 / 2", "6 / 4", "7 / 2", "-7 / 2", "7 / -2", "7 % 2", "-7 % 2", "7 % -2", "-7 % -2", "7.5 % 2", "-7.5 % 2", "7.5 % -2", "7 % 2.5",
            "0 % 5", "-0 % 5", "5 % 5", "5.5 % 5.5", "1e20 % 7", "1e300 % 7", "7 % 1e300", "-7 % 1e300", "7 % 1e-300", "1 % 0.1", "0.3 % 0.1", "5 % inf", "10 % 3 % 2",
            "10 % (3 % 2)", "2 * 7 % 3", "2 + 7 % 3", "7 % 3 * 2", "2 ^ 7 % 3", "7 % 3 ^ 2", "100 % 7 mm", "100 mm % 7", "100 mm % 7 mm", "100 mm % 7 s", "-100 mm % 7",
            "100 mm % -7", "100 mm % 0", "100 mm % 0.0", "5.5 mm % 2", "(5 mm) % (2 mm)", "(5 mm) % (2 s)", "5 % (2 mm)", "5.5 % (2 mm)", "(5 mm) % sin(30)",
            "sin(90) % 2", "sin(90) % sin(30)", "7 % sin(90)", "sin(90) * 7 % 2", "mod(sin(90) * 7; 2)", "1 mm * 1 mm * 1 mm * 1 mm * 1 mm * 1 mm * 1 mm * 1 mm",
            "1 mm * 1 mm * 1 mm * 1 mm * 1 mm * 1 mm * 1 mm", "1 / (1 mm * 1 mm * 1 mm * 1 mm * 1 mm * 1 mm * 1 mm * 1 mm * 1 mm)", "1 / (1 mm^8)", "1 / (1 mm^7)", "1 mm^-8",
            "1 mm^-9", "1 mm^8", "1 mm^7", "(1 mm^4) * (1 mm^4)", "(1 mm^4) * (1 mm^3)", "(1 mm^4) / (1 mm^-4)", "(1 mm^4) / (1 mm^-3)", "(1 mm^-4) / (1 mm^4)",
            "(1 mm^-4) / (1 mm^5)", "(1 mm^4)^2", "(1 mm^4)^1", "(1 mm^-4)^2", "(1 mm^2)^3", "(1 mm^2)^4", "(1 mm^2)^-4", "(1 mm^2)^-5", "(1 mm)^1.5", "(1 mm^2)^1.5",
            "(1 mm^2)^0.5", "(1 mm)^0.5", "(1 mm)^0", "(1 mm)^-0", "(1 mm)^100", "(1 mm)^1000", "(1 mm)^-100", "(1 mm)^200", "(1 mm)^255", "(1 mm)^256", "(1 mm)^257",
            "(1 mm)^300", "(1 mm)^(sin(90)*100)", "(1 mm)^sin(90)", "(2 mm)^sin(90)", "(2 mm)^(sin(30)*2)", "(2 mm)^(sin(30)*4)", "(2 mm)^sqrt(4)", "(2 mm)^sqrt(2)", "(2 mm)^cos(60)",
            "(2 mm)^(1 mm)", "(2 mm)^(1 mm/1 mm)", "(2 mm)^(pRat*2)", "(2 mm)^pCnt", "(2 mm)^pRat", "(2 mm)^(pLen/pLen)", "(2 mm)^round(2.2)", "(2 mm)^(-pCnt)",
            "2^(pLen/pLen)", "2^sqrt(4)", "2^pCnt", "2^pRat", "2.5^pCnt", "pCnt^2.5", "pCnt^pRat", "pRat^pCnt", "pRat^sin(90)", "pCnt^sin(90)", "True^2", "2^True", "True^True",
            "False^False", "False^-1", "True^-1", "(-True)^0.5", "pCnt^-1", "pCnt^-pCnt", "(-pCnt)^pRat", "(-3)^pRat", "(-3.0)^2", "(-3.5)^2", "(-3.5)^3", "(-3.5)^2.5", "(-3.5)^-2",
            "(-3.5)^-3", "(-3.5)^-2.5", "(-0.0)^-1", "(-0.5)^-2", "(-0)^-1", "1/(-0)", "1/0.0", "1.0/0", "0.0/0", "0/0", "0/0.0", "1 mm / (0 mm)", "0 mm / 0 mm", "-1 mm / 0",
            "1 / (0 mm)", "-1 / (0 mm)", "0 / (0 mm)", "pLen / 0", "pLen / 0.0", "pCnt / 0", "pCnt / 0.0", "pRat / 0", "pRat / 0.0", "1 / pRat", "1 / (pRat - 0.5)", "1 / (pCnt - 3)",
            "1 / (pLen - pLen)", "1 / (pLen - 10 mm)", "True / 0", "True / False", "1 / False", "1 / (False)", "2 / True", "True / 2"]
    return [("py", t) for t in out]


def geometry():
    """Vectors and the functions on them; the others (matrix, placement, rotation) as far as their argument checks go."""
    nums = ["0", "1", "-1", "2.5", "3 mm", "1 cm", "pCnt", "pRat", "pLen", "True", "<<a>>", "None", "sin(30)", "30 deg"]
    vs = ["vector(1;0;0)", "vector(0;1;0)", "vector(1;2;3)", "vector(4;5;6)", "vector(0;0;0)", "vector(1 mm;2 mm;3 mm)", "vector(-1;2;-3)",
          "vector(0.1;0.2;0.3)", "vector(3;4;0)", "vector(1;1;0)", "vector(0;0;1)", "vector(2;0;0)"]
    out = []
    for a, b, c in itertools.islice(itertools.product(nums, nums, nums), 0, None, 7):
        out.append(f"vector({a};{b};{c})")
    out += ["vector()", "vector(1)", "vector(1;2)", "vector(1;2;3;4)", "vector(1,2,3)", "vector(1, 2, 3)", "vector(list(1;2;3))", "vector(1;2;pi)", "vector(pi;e;1/3)"]
    out += vs
    for a, b in itertools.product(vs[:7], vs[:7]):
        out += [f"{a} + {b}", f"{a} - {b}", f"{a} * {b}", f"{a} / {b}", f"{a} % {b}", f"{a} ^ {b}", f"{a} == {b}", f"{a} != {b}", f"{a} < {b}", f"{a} >= {b}"]
    for v in vs[:6]:
        for x in nums:
            out += [f"{v} * {x}", f"{x} * {v}", f"{v} / {x}", f"{x} / {v}", f"{v} + {x}", f"{x} + {v}", f"{v} - {x}", f"{x} - {v}", f"{v} % {x}", f"{x} % {v}", f"{v} ^ {x}",
                    f"{x} ^ {v}", f"{v} == {x}", f"{x} != {v}", f"{v} < {x}", f"{x} > {v}"]
        out += [f"-{v}", f"+{v}", f"{v} ? 1 : 2", f"str({v})", f"list({v}; {v})", f"tuple({v})", f"abs({v})", f"sin({v})", f"sum({v}; {v})", f"max({v}; 1)", f"not({v})",
                f"{v} + {v} + {v}", f"2 * {v} - {v}", f"({v} + {v}) / 2", f"{v} * 0", f"{v} / 0", f"{v} / 0.0", f"{v} / (0 mm)", f"{v} * (1/0)", f"{v} * 1e308 * 10"]
    for f in ["vnormalize", "vscalex", "vscaley", "vscalez", "vscale", "vangle", "vcross", "vdot", "vlinedist", "vlinesegdist", "vlineproj", "vplanedist", "vplaneproj"]:
        arity = {"vnormalize": 1, "vscalex": 2, "vscaley": 2, "vscalez": 2, "vscale": 4, "vangle": 2, "vcross": 2, "vdot": 2, "vlinedist": 3, "vlinesegdist": 3, "vlineproj": 3,
                 "vplanedist": 3, "vplaneproj": 3}[f]
        scal = f.startswith("vscale")
        for args in itertools.islice(itertools.product(vs[:9], repeat=arity), 0, None, max(1, len(vs[:9]) ** arity // 120)):
            if scal:
                args = (args[0],) + tuple(["2", "3 mm", "0.5", "-1"][i % 4] for i in range(arity - 1))
            out.append(f"{f}({'; '.join(args)})")
        out += [f"{f}({'; '.join(['1'] * arity)})", f"{f}({'; '.join(['vector(1;2;3)'] + ['1 s'] * (arity - 1))})", f"{f}({'; '.join(['vector(1;2;3)'] + ['<<a>>'] * (arity - 1))})",
                f"{f}({'; '.join(['vector(1;2;3)'] + ['1 mm'] * (arity - 1))})", f"{f}({'; '.join(['vector(1;2;3)'] + ['vector(3;2;1)'] * (arity - 1))})",
                f"{f}({'; '.join(['1 mm'] * arity)})", f"{f}({'; '.join(['<<a>>'] * arity)})", f"{f}({'; '.join(['None'] * arity)})"]
    out += ["vscalex(vector(1;2;3); 1 deg)", "vscale(vector(1;2;3); 1; 2; 1 s)", "vscale(vector(1;2;3); 1; <<a>>; 3)", "vscaley(vector(1;2;3); True)", "vscalez(vector(1;2;3); pLen)",
            "vscalez(vector(1;2;3); pAng)", "vlinedist(vector(0;1;0); vector(0;0;0); vector(0;0;0))", "vlinedist(vector(0;0;0); vector(1;1;1); vector(1;1;1))",
            "vangle(vector(0;0;0); vector(1;0;0))", "vangle(vector(1;0;0); vector(1;0;0))", "vangle(vector(1;0;0); vector(-1;0;0))", "vangle(vector(1;0;0); vector(0;1;0))",
            "vangle(vector(1;1e-17;0); vector(1;0;0))", "vnormalize(vector(0;0;0))", "vnormalize(vector(1e200;1e200;0))", "vnormalize(vector(1e-200;0;0))",
            "vplaneproj(vector(1;2;3); vector(0;0;0); vector(0;0;0))", "vplanedist(vector(1;2;3); vector(0;0;0); vector(0;0;0))", "vlinesegdist(vector(1;2;3); vector(0;0;0); vector(0;0;0))",
            "vlineproj(vector(1;2;3); vector(1;0;0); vector(0;0;0))"]
    out += ["create(<<vector>>)", "create(<<Vector>>; 1; 2; 3)", "create(<<VECTOR>>; 1)", "create(<<vector>>; list(1;2;3))", "create(<<vector>>; tuple(1;2;3))", "create(<<vector>>; vector(1;2;3))",
            "create(<<vector>>; 1; 2)", "create(<<vector>>; 1; 2; 3; 4)", "create(<<vector>>; <<a>>)", "create(<<vector>>; list(1;2))", "create(<<vector>>; 1 mm; 2 mm; 3 mm)", "create(1)", "create(<<nothing>>)",
            "create(<<matrix>>)", "create(<<matrix>>; 1)", "create(<<placement>>)", "create(<<rotation>>)", "create(<<rotation>>; 1; 2; 3)", "create(<<vector>>; pStr)", "create(pStr)", "create(pStr; 1; 2; 3)"]
    # what the matrix functions check before they would make a matrix
    for f in ["minvert", "mrotate", "mrotatex", "mrotatey", "mrotatez", "mscale", "mtranslate", "translationm", "rotationx", "rotationy", "rotationz", "matrix", "placement", "rotation"]:
        for a in ["1", "1 mm", "<<a>>", "vector(1;2;3)", "list(1;2;3)", "tuple(1;2;3)", "list(1;2)", "pLen", "None", "30 deg", "90"]:
            out += [f"{f}({a})", f"{f}({a}; 1)", f"{f}({a}; 30 deg)", f"{f}({a}; 1 mm)", f"{f}({a}; 1; 2)", f"{f}({a}; 1; 2; 3)", f"{f}({a}; {a})", f"{f}(1; {a})"]
    return [("geom", t) for t in out]


# Units of one kind of quantity, for the conversions between them.
UNIT_GROUPS = [
    ["nm", "um", "µm", "mm", "cm", "dm", "m", "km", "in", "\"", "ft", "'", "thou", "mil", "yd", "mi"],
    ["ug", "µg", "mg", "g", "kg", "t", "lb", "lbm", "oz", "st", "cwt"], ["s", "min", "h"], ["A", "nA", "uA", "µA", "mA", "kA", "MA"], ["K", "mK", "µK", "uK"],
    ["mol", "nmol", "µmol", "umol", "mmol"], ["N", "mN", "kN", "MN", "lbf"], ["Pa", "kPa", "MPa", "GPa", "bar", "mbar", "Torr", "mTorr", "uTorr", "µTorr", "psi", "ksi", "Mpsi"],
    ["W", "nW", "uW", "µW", "mW", "kW", "VA"], ["J", "mJ", "kJ", "Nm", "Nmm", "VAs", "CV", "Ws", "kWh", "eV", "keV", "MeV", "cal", "kcal"], ["V", "kV", "mV"],
    ["S", "MS", "kS", "mS", "uS", "µS"], ["Ohm", "kOhm", "MOhm"], ["F", "mF", "µF", "uF", "nF", "pF"], ["H", "mH", "µH", "uH", "nH"], ["T", "mT", "G"],
    ["°", "deg", "rad", "gon", "M", "′", "AS", "″"], ["Hz", "kHz", "MHz", "GHz", "THz"], ["l", "ml", "cft"], ["sqft", "mm^2", "m^2"], ["mph", "m/s", "mm/s", "km/h"], ["C", "A*s"], ["Wb", "T*m^2"],
]


def unit_conversions():
    out = []
    for g in UNIT_GROUPS:
        for a, b in itertools.product(g, g):
            out += [f"1 {a} + 1 {b}", f"2.5 {a} - 1 {b}", f"1 {a} == 1 {b}", f"1 {a} < 1 {b}", f"(1 {a}) / (1 {b})", f"1 {a} * 1 {b}"]
        for a in g:
            out += [f"1 {a}", f"-{a}" if False else f"(1 {a})^2", f"sqrt(4 {a}^2)", f"10 {a} / 4"]
    return [("uconv", t) for t in out]


def mutations(n=5000, seed=26):
    """Valid expressions with a character deleted, doubled, swapped or replaced: mostly refused, and every refusal is a test."""
    rng = random.Random(seed + SEED)
    base = [t for c, t in random_trees(1200, seed=7)] + [t for c, t in functions()[::37]] + [t for c, t in strings()] + [t for c, t in freecad_tests()] + [t for c, t in geometry()[::41]]
    alphabet = list("()+-*/%^?:,;.<>=!#@[]\"'") + [" ", "1", "a", "e", "m", "s", "µ", "_", "$", "&", "|", "~"]
    out = []
    for _ in range(n):
        t = rng.choice(base)
        if not t:
            continue
        i = rng.randrange(len(t))
        k = rng.random()
        if k < 0.3:
            t = t[:i] + t[i + 1:]
        elif k < 0.5:
            t = t[:i] + t[i] * 2 + t[i + 1:]
        elif k < 0.7:
            t = t[:i] + rng.choice(alphabet) + t[i + 1:]
        elif k < 0.9:
            t = t[:i] + rng.choice(alphabet) + t[i:]
        else:
            j = rng.randrange(len(t))
            i, j = min(i, j), max(i, j)
            t = t[:i] + t[j:i:-1][:0] + t[i:j][::-1] + t[j:]
        out.append(("mutate", t))
    return out


def spacing_and_letters():
    out = []
    for t in ["1 + 2", "1+\n2", "1\n+\n2", "1\t+\t2", "\n1 + 2\n", "sin(\n30)", "sin(30\n)", "sin(30;\n1)", "min(1;\n2)", "min(1;\t2)", "1 mm\n+ 1 mm", "1\nmm", "1\tmm", "1 \t\n mm",
              "<<a\nb>> + <<c>>", " 1", "1 ", "  1  +  2  ", "(\n1\n)", "1 ?\n2 :\n3", "pLen\n.x", "pLen.\nValue", "p\nLen", "1 +\r2", "1\r+2", "\r1", "1\x0b+2", "1\x0c+2", "1 \u00a0+ 2", "1\u2003+2"]:
        out.append(t)
    letters = ["α", "β", "μ", "µ", "Ω", "Ω", "Å", "ä", "é", "ñ", "日", "本", "ж", "ß", "ǅ", "ʰ", "ª", "²", "³", "¼", "٣", "Ⅷ", "a\u0301", "\u0301a", "e\u0301", "𝒜", "😀", "ℵ", "‿", "·"]
    for c in letters:
        out += [c, f"{c}1", f"a{c}", f"{c}a", f"1 {c}", f"{c} + 1", f"{c}m", f"1 {c}m", f"m{c}", f"1 m{c}", f"{c}(1)", f"{c}_x", f"x@{c}", f"1{c}", f"({c})", f"sin({c})", f"{c}.x", f"x.{c}", f"<<{c}>>", f"str({c})"]
    for c in ["µm", "μm", "µA", "μA", "µg", "μg", "µs", "μs", "µ", "μ", "1 µm", "1 μm", "2 µA + 1 uA", "2 μA + 1 uA", "1 µ", "1 μ", "µ(1)", "μ(1)", "Ω", "1 Ω", "1 Ohm", "1 ohm", "1 OHM", "1 Mm", "1 Km", "1 KM", "1 MM", "1 CM", "1 Mg", "1 GG", "1 kΩ"]:
        out.append(c)
    return [("lex2", t) for t in out]


def formatting_and_math():
    out = []
    formats = ["%d", "%5d", "%-5d|", "%05d", "%+d", "% d", "%i", "%u", "%x", "%X", "%o", "%#x", "%#o", "%e", "%E", "%f", "%F", "%g", "%G", "%.0f", "%.1f", "%.3e", "%10.4f", "%-10.4f|", "%+.2f",
               "%s", "%10s|", "%-10s|", "%.2s", "%r", "%a", "%c", "%%", "%5%", "%(a)s", "%*d", "%.*f", "%ld", "%hd", "%lld", "%5.3d", "%.0d", "%#.3g", "%#g", "%08.3f", "%+08.3f", "%-+8.3f|", "%.10g", "%.15g", "%.17g", "%s and %s", "%s %%", "%d%%"]
    fargs = ["0", "1", "-1", "42", "3.14159", "-2.5", "1e10", "1e-5", "0.5", "1.5", "2.5", "255", "<<a>>", "<<abc>>", "True", "None", "pLen", "1 mm", "2^70", "1e20", "list(1;2)", "tuple(1;2)", "tuple(1;2;3)",
             "1/3", "2/3", "1e22/3", "123456.789", "pRat", "pCnt", "pStr", "sin(30)", "1e308*10", "-1e308*10", "(1e308*10)/(1e308*10)", "0.1+0.2", "-0.0", "1e-7/3", "999999.5", "0.0001234", "123456789012"]
    for f in formats:
        for a in fargs:
            out.append(f"<<{f}>> % {a}")
    values = ["0", "-0.0", "1", "-1", "0.5", "-0.5", "2", "2.5", "10", "100", "1e-9", "1e-300", "1e-320", "1e300", "1e308", "1e308*10", "-1e308*10", "(1e308*10)/(1e308*10)", "pi", "e", "pi/2", "pi/4", "30", "45", "60", "90", "180", "270", "360", "720",
              "1e9", "1e15", "1e16", "1/3", "0.1+0.2", "123456.789", "710", "709.78", "-745.2", "-746", "1000", "50", "0.9999999999999999", "1.0000000000000002", "-0.9999999999999999", "37", "3", "27", "64", "-8", "-27"]
    for f in ["sin", "cos", "tan", "asin", "acos", "atan", "sinh", "cosh", "tanh", "exp", "log", "log10", "sqrt", "cbrt", "ceil", "floor", "round", "trunc", "abs", "not", "str"]:
        for v in values:
            out.append(f"{f}({v})")
            if f in ("sin", "cos", "tan"):
                out += [f"{f}({v} deg)", f"{f}({v} rad)"]
            if f in ("sqrt", "cbrt", "abs", "ceil", "floor", "round", "trunc", "str"):
                out.append(f"{f}({v} mm)")
    twos = ["0", "1", "-1", "2", "-2", "0.5", "-0.5", "3", "10", "1e300", "1e-300", "pi", "1e308*10", "(1e308*10)/(1e308*10)", "-0.0"]
    for f in ["atan2", "mod", "pow", "hypot", "cath"]:
        for a, b in itertools.product(twos, twos):
            out.append(f"{f}({a}; {b})")
    # str() and the layout of a float
    floats = ["1", "1.5", "0.1", "0.0001", "0.00001", "0.000123", "123456789.123", "1e15", "1e16", "1e17", "123456789012345678", "0.1+0.2", "1/3", "2/3", "1e22/3", "1e-7/3", "5e-324*1", "1.7976931348623157e308",
              "100000000000000.0/3", "1000000000000000.0/3", "10000000000000000.0/3", "1e15/7", "1e16/7", "1e-4/3", "1e-5/3", "-0.0", "-1e-7", "25.4", "304.8", "0.30000000000000004*10", "4.35*100", "1.005*1000", "2^0.5", "10^-5", "10^-4"]
    for x in floats:
        out += [f"str({x})", f"str({x} mm)", f"str({x} deg)", f"str(sin(0) + {x})", f"str(list({x}))", f"str(tuple({x};{x}))", f"<<%s>> % ({x})", f"<<%r>> % ({x})", f"<<%f>> % ({x})", f"<<%g>> % ({x})", f"<<%e>> % ({x})"]
    return [("fmt", t) for t in out]


def more_fuzz():
    """Number-like strings, identifier-like strings, and valid expressions with white space put in, at random."""
    rng = random.Random(77 + SEED)
    out = []
    for _ in range(2500):
        k = rng.choice([1, 2, 3, 4, 5, 6, 8, 10])
        out.append(("numfuzz", "".join(rng.choice("0123456789012345678.,.,eE+-xmsb _") for _ in range(k))))
    for _ in range(2500):
        k = rng.choice([1, 2, 3, 4, 5, 6, 8])
        out.append(("idfuzz", "".join(rng.choice("abcdefmMnpsStTuUVWxyzAEPCDLNO0123456789_@$.#µé") for _ in range(k))))
    valid = [t for c, t in random_trees(1500, seed=12)] + [t for c, t in functions()[::53]] + [t for c, t in geometry()[::97]] + [t for c, t in strings()[::3]]
    gaps = [" ", " ", "  ", "\t", "\n", "\r", "\x0b", "\x0c", "\x10", "\u00a0"]
    for _ in range(3500):
        t = rng.choice(valid)
        for _k in range(rng.choice([1, 1, 2, 3])):
            i = rng.randrange(len(t) + 1)
            t = t[:i] + rng.choice(gaps) + t[i:]
        out.append(("wsfuzz", t))
    return out


def trigonometry():
    """The angles and ratios a drawing uses, one by one: sin, cos and tan of whole degrees, the inverse functions of tenths."""
    out = []
    for d in range(0, 721):
        out += [f"sin({d})", f"cos({d})", f"tan({d} deg)"]
    for d in range(0, 361, 5):
        out += [f"sin({d} deg) * 100 mm", f"cos({d} deg) * cos({d} deg) + sin({d} deg) ^ 2", f"{d} deg * 2 / 3"]
    for k in range(-100, 101):
        v = k / 100
        out += [f"asin({v})", f"acos({v})", f"atan({v})", f"atan2({v}; 0.5)", f"sinh({v * 3})", f"cosh({v * 3})", f"tanh({v * 3})", f"exp({v * 5})", f"log({abs(v) + 0.5})", f"log10({abs(v) * 10 + 1})",
                f"sqrt({abs(v) * 10})", f"cbrt({v * 30})", f"{abs(v) * 7 + 1} ^ {v * 2}", f"pow({abs(v) + 1}; {v})"]
    return [("trig", t) for t in out]


def freecad_tests():
    out = ["0 mm", "-5 mm", "+5 mm", "1.25 mm", "1.0e3 mm", "1mm + 1mm", "5mm +- 1mm", "1mm * 3", "1 m", "1 m + 25 mm", "(5mm + 1cm) / 3", "10 deg", "360 deg + pi rad",
           "True mm", "mm", "-", "10 bogusunits", "1.25 mm kg", "*1", "sqrt", "sqrt()", "sqrt(1, 2)", "1 mm * 2 cm", "2 cm * 1 mm", "(1 m - 750 mm) * 3", "(5 mm)^2",
           "24 V / (2 A)", "10 mm * kg", "1234000.00 mm*kg/s^2", "0", "1 / 2", "40 mm / (2 cm)", "sqrt(9 mm^2)", "pow(2 mm, 3)", "sum(1 mm, 2 mm, 3 mm)",
           "list(1 mm, 2 mm)[0]", "<<(Line 1\\nLine 2)>>", "atan2(1 mm, 1 mm)", "vector(1 mm, 2 mm, 3 mm)", "vector(1, 0, 0) * 5 mm", "pow(2, 3) * mm^3",
           "(vector(1 mm,2 mm,3 mm)[0]) * 2", "Placement.Base.x", "Sketch.Foo", "2*(5%3)", "6*9", "42", ".Placement.Base.x + 10mm", "=-(Cylinder.Radius + Box.Length - 1\"/2)",
           "-(Cylinder.Radius + Box.Length - 1\"/2)", "1\"/2", "1\"/2 + 1", "pow(1,234)", "sqrt(1,234)", "pow(1;234)", "pow(1, 234)", "pow(1 234; 2)", "pow(1,234.5)",
           "pow((1,234.5), 2)", "12,345.67 mm", "1,234 mm", "1.234 mm", "(12,345.67 mm)", "Box001.Length001 + 2 mm", "parsequant(1 mm)", "10 g", "30 kg",
           "1 kg + 20010 g", "1 s + 1 min", "1 min + 1 s", "1 h - 1 min", "1 mi + 1 ft", "1 yd - 1 ft", "1 thou + 1 mil", "1 lbf", "1 kip", "1 psi + 1 Pa",
           "2 * 3 mm", "2 mm * 3", "3 / 2 mm", "3 mm / 2", "3 mm / 2 mm", "3 mm / 2 s", "3 mm / 2 mm^2", "1/2 mm", "1 / 2 mm", "1 /2 mm", "(1/2) mm", "1 mm/s^2", "2 * 1 mm/s^2",
           "1 m/s ^ 2", "1 m/s^2 * 2", "2 m / s", "2 m / s ^ 2", "2 m / (s ^ 2)", "2 m /s^2", "2 m / s^2 / s", "2 m * s", "2 m s", "2 (m)", "2 (m*s)", "2 (m/s)", "2 (m)(s)",
           "(2) (m)", "(2) m", "(2) m/s", "(2 + 1) m/s", "(2 + 1) m/s^2", "(2 + 1) m s", "(2 + 1) (m s)", "(2) m^2", "(2) m^-2", "(2) m^2 s", "2 m^2 s", "2 m^2/s^2",
           "2 m/s/s", "2 m/s*s", "2 m*s/s", "2 m*s*s", "2 mm^2 / 3 mm^2", "2 mm^2 * 3 mm^2", "2^3 mm", "2 ^ 3 mm", "2 mm ^ 3", "2 mm ^ 3 mm", "2 mm ^ -3", "2 mm ^ - 3",
           "2 mm ^ (3)", "2 mm ^ 3.0", "2 mm ^ 3.5", "2 mm ^ +3", "2 mm ^ 1", "2 mm ^ 0", "2 mm ^ 00", "2 mm ^ 1e0", "2 mm ^ 2^2", "2 mm ^ 2 ^ 2", "2 mm^2^2", "2 mm^2 mm", "2 mm^2^-2"]
    return [("fctest", t) for t in out]


class _Tree:
    """Random well-formed expressions: atoms, unary signs, binary operators, conditionals, functions."""

    def __init__(self, rng):
        self.rng = rng
        self.atoms = ["1", "2", "3", "4", "0", "10", "0.5", "2.5", "1e3", "pi", "e", "True", "False", "None", "pCnt", "pRat", "pLen", "pAng", "pOn", "pStr",
                      "<<s>>", "1 mm", "2 mm", "3 cm", "0.5 m", "1 in", "2 s", "1 kg", "30 deg", "1 rad", "2 mm^2", "1 mm/s", "sin(30)", "cos(60)", "sqrt(4)", "round(2.5)",
                      "abs(-3)", "min(1;2)", "max(1 mm;2 mm)", "hypot(3;4)", "atan2(1;1)", "mod(7;3)", "pow(2;3)", "list(1;2)", "str(5)"]
        self.funcs1 = ["abs", "sqrt", "sin", "cos", "tan", "round", "floor", "ceil", "trunc", "exp", "log", "not", "str", "cbrt", "asin", "atan"]

    def sp(self):
        return self.rng.choice(["", " ", " ", " ", "  "])

    def gen(self, depth):
        r = self.rng
        if depth <= 0 or r.random() < 0.18:
            return r.choice(self.atoms)
        k = r.random()
        if k < 0.50:
            op = r.choice(BINOPS)
            return f"{self.gen(depth - 1)}{self.sp()}{op}{self.sp()}{self.gen(depth - 1)}"
        if k < 0.60:
            return f"{r.choice(['-', '+'])}{self.gen(depth - 1)}"
        if k < 0.72:
            return f"({self.gen(depth - 1)})"
        if k < 0.80:
            return f"{self.gen(depth - 1)} ? {self.gen(depth - 1)} : {self.gen(depth - 1)}"
        if k < 0.92:
            return f"{r.choice(self.funcs1)}({self.gen(depth - 1)})"
        if k < 0.96:
            return f"{r.choice(['min', 'max', 'sum', 'hypot', 'atan2', 'mod', 'pow', 'average'])}({self.gen(depth - 1)}; {self.gen(depth - 1)})"
        return f"({self.gen(depth - 1)}) {r.choice(['mm', 's', 'kg', 'deg', 'm/s', 'mm^2'])}"


def random_trees(n=2600, seed=3160):
    rng = random.Random(seed + SEED)
    tree = _Tree(rng)
    return [("rand", tree.gen(rng.choice([1, 2, 2, 3, 3, 4]))) for _ in range(n)]


TOKENS = ["1", "2", "3", "0.5", "1e3", "1,5", "mm", "s", "kg", "deg", "m", "in", "\"", "'", "pi", "e", "True", "None", "pLen", "pCnt", "x", "(", ")", "(", ")", "+",
          "-", "*", "/", "%", "^", "?", ":", "==", "!=", "<", "<=", ">", ">=", ",", ";", "sin(", "min(", "sum(", "<<a>>", "[", "]", ".", "=", "!", "@", "#", "$",
          "{", "}", "&", "|", "~", "`", "\\", "µ", "°", "é", "A1", ":", "pLen.x", "1 mm", "2 s", "<<", ">>", "mm^2", "^2", "^-1", "-1"]


def token_fuzz(n=3200, seed=11965):
    rng = random.Random(seed + SEED)
    out = []
    for _ in range(n):
        k = rng.choice([1, 2, 2, 3, 3, 3, 4, 4, 5, 6, 7, 8])
        sep = rng.choice(["", " ", " ", " "])
        out.append(("fuzz", sep.join(rng.choice(TOKENS) for _ in range(k))))
    return out


def lexical():
    """Single characters and short runs, the ones flex's default rule skips and the ones with a rule."""
    out = []
    for c in list("!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~") + ["\t", "\r", "\n", "\x0b", "\x0c", "\x10", " ", "−", "–", "—", "×", "÷",
                                                          "€", "£", "¬", "∞", "√", "π", "µ", "°", "′", "″", "½", "²", "³", "٣", "１", "ǅ", "Ⅷ", "ä", "ß", "Ω", "日", "😀", "‰"]:
        out += [f"1 {c} 2", f"1{c}2", f"{c}1", f"1{c}", f"{c}", f"1 {c}", f"{c} 1", f"a{c}b", f"2 mm {c} 3 mm", f"sin(30{c})", f"sin({c}30)", f"{c}sin(30)", f"{c}mm"]
    for t in ["1 − 1", "1−1", "−1", "1 - −1", "2 mm − 1 mm", "1 + − 1", "−− 1", "1 – 1", "1 — 1",
              "1 2", "1 mm", "2 mm", "2 mm + 1 mm", "﻿1", "1﻿", "1 ​+ 1"]:
        out.append(t)
    for t in ["sin(30)", "sin(30 )", "sin( 30)", "sin\t(30)", "sin\x10(30)", "sin\n(30)", "sin\r(30)", "sin  (30)", " sin(30)", "SIN(30)", "Sin(30)", "sin(30)(30)", "_sin(30)", "sin_(30)",
              "sin1(30)", "s1n(30)", "ésin(30)", "sinus(30)", "sinh(30)", "cosh(30)", "a(30)", "x(30)", "x (30)", "pLen(30)", "pLen (30)", "min(1)", "min (1)",
              "1 min", "1 min (1)", "min", "1 min + 1 s", "1 s + 1 min", "1 min(1)", "m(1)", "mm(1)", "1 m(1)", "(1 m)(1)", "e(1)", "pi(1)", "True(1)", "None(1)", "A1(1)", "$A$1(1)"]:
        out.append(t)
    return [("lex", t) for t in out]


def cases():
    items = []
    for gen in (numbers, literals_with_units, unit_pairs, unit_powers, building_units, operators, conditionals, functions, constants, strings,
                variables, python_semantics, geometry, freecad_tests, lexical, unit_conversions, spacing_and_letters, formatting_and_math, trigonometry):
        items += gen()
    items += random_trees()
    items += token_fuzz()
    items += token_fuzz(2600, seed=401)
    items += mutations()
    items += more_fuzz()
    items += random_trees(9000, seed=2026)
    return _uniq(items)


if __name__ == "__main__":
    import collections
    cs = cases()
    print(len(cs), dict(collections.Counter(c for c, _ in cs)))
