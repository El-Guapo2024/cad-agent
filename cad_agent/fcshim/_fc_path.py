# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses FreeCAD's Path::Command and Path::Toolpath and keeps FreeCAD's licence, the GNU
# Lesser General Public License, version 2.1 or (at your option) any later version; the text is in ../../ui/LICENSE.
#
#   Derived from: src/Mod/CAM/App/Command.cpp, CommandPyImp.cpp, Path.cpp, PathPyImp.cpp,
#                 PathSegmentWalker.cpp (Copyright (c) 2014 Yorik van Havre), FreeCAD
#                 (https://github.com/FreeCAD/FreeCAD), commit 3160daf1e2b62b0472854da4848255c6b3ad554c
#
# See ../../NOTICE.
"""Path.Command and Path.Path as FreeCAD's C++ gives them to Python: a command's parameters are a map sorted by
name (std::map), Command.Parameters hands out a cached dict (parameters_copy_dict) as CommandPy does, toGCode is
Command::toGCode's integer rounding, and Path.Commands is a list of copies."""
from __future__ import annotations

import math

from ._fc_base import BoundBox, Placement, Rotation, Vector


def _num(v, what="The dictionary can only contain number values"):
    if isinstance(v, (int, float)):           # PyLong (bool included) or PyFloat, as CommandPy checks
        return float(v)
    raise TypeError(what)


class BadFormatError(ValueError):
    pass


class Command:
    __slots__ = ("_name", "_params", "_ann", "_cache")

    def __init__(self, name="", parameters=None, annotations=None):
        object.__setattr__(self, "_name", "")
        object.__setattr__(self, "_params", {})
        object.__setattr__(self, "_ann", {})
        object.__setattr__(self, "_cache", None)
        if isinstance(parameters, Placement):
            if name:
                self._set_from_gcode(name)
            self._set_from_placement(parameters)
            return
        if parameters is not None and not isinstance(parameters, dict):
            raise TypeError("Command(name, parameters): parameters must be a dict or a Placement")
        if name:
            self._set_from_gcode(str(name))
        for k, v in (parameters or {}).items():
            if not isinstance(k, str):
                raise TypeError("The dictionary can only contain string keys")
            self._params[k.upper()] = _num(v)
        for k, v in (annotations or {}).items():
            if not isinstance(k, str):
                raise TypeError("The annotations dictionary can only contain string keys")
            if isinstance(v, str):
                self._ann[k] = v
            elif isinstance(v, (int, float)):
                self._ann[k] = float(v)
            else:
                raise TypeError("The annotations dictionary can only contain string or number values")

    # ── Command.cpp ──
    def _p(self, k, default=0.0):
        return self._params.get(k, default)

    def _placement(self, pos=None):
        pos = pos or Vector()
        v = Vector(self._p("X", pos.x), self._p("Y", pos.y), self._p("Z", pos.z))
        r = Rotation()
        r._set_ypr(self._p("A"), self._p("B"), self._p("C"))
        return Placement(v, r)

    def _set_from_gcode(self, s):
        self._params.clear()
        self._ann.clear()
        gcode_part, annotation_part = s, ""
        cpos = s.find("; ")
        if cpos != -1:
            gcode_part, annotation_part = s[:cpos], s[cpos + 1:]
        mode, key, value = "none", "", ""
        name = self._name
        for i, ch in enumerate(gcode_part):
            if ch.isdigit() or ch == "-" or ch == "." or (ch == "e" and i > 0 and gcode_part[i - 1].isdigit()):
                value += ch
            elif ch.isalpha():
                if mode == "command":
                    if key and value:
                        name = (key + value).upper()
                        key, value = "", ""
                        mode = "argument"
                    else:
                        raise BadFormatError("Badly formatted GCode command")
                    mode = "argument"
                elif mode == "none":
                    mode = "command"
                elif mode == "argument":
                    if key and value:
                        self._params[key.upper()] = _atof(value)
                        key, value = "", ""
                    else:
                        raise BadFormatError("Badly formatted GCode argument")
                elif mode == "comment":
                    value += ch
                key = ch
            elif ch == "(":
                mode = "comment"
            elif ch == ")":
                key = "("
                value += ")"
            else:
                if mode == "comment":
                    value += ch
        if annotation_part:
            self._set_annotations(annotation_part)
        if key and value:
            if mode in ("command", "comment"):
                cmd = key + value
                name = cmd.upper() if mode == "command" else cmd
            else:
                self._params[key.upper()] = _atof(value)
        else:
            raise BadFormatError("Badly formatted GCode argument")
        object.__setattr__(self, "_name", name)

    def _set_annotations(self, text):
        for tok in text.split():
            if ":" not in tok:
                continue
            k, v = tok.split(":", 1)
            if len(v) >= 2 and v[0] == "'" and v[-1] == "'":
                self._ann[k] = v[1:-1]
            else:
                try:
                    self._ann[k] = float(v)
                except ValueError:
                    self._ann[k] = v

    def _set_from_placement(self, pl):
        object.__setattr__(self, "_name", "G1")
        self._params.clear()
        p = pl._pos
        a, b, c = pl._rot.getYawPitchRoll()
        for k, v in (("X", p.x), ("Y", p.y), ("Z", p.z), ("A", a), ("B", b), ("C", c)):
            if v != 0.0:
                self._params[k] = v

    def _to_gcode(self, precision=6, padzero=True):
        out = [self._name]
        if precision < 0:
            precision = 0
        scale = math.pow(10.0, precision + 1)
        iscale = int(scale) // 10
        for k in sorted(self._params):
            if k == "N":
                continue
            s = " " + k
            v = int(self._params[k] * scale)              # static_cast<std::int64_t>, toward zero
            if v < 0:
                v = -v
                s += "-"
            v += 5
            v //= 10
            s += str(v // iscale)
            if precision:
                width = precision
                digits = v % iscale
                if not padzero:
                    if not digits:
                        out.append(s)
                        continue
                    while digits % 10 == 0:
                        digits //= 10
                        width -= 1
                s += "." + str(digits).rjust(width, "0")
            out.append(s)
        text = "".join(out)
        if self._ann:
            parts = []
            for k in sorted(self._ann):
                v = self._ann[k]
                parts.append(f"{k}:'{v}'" if isinstance(v, str) else f"{k}:{v:.6f}")
            text += "; " + " ".join(parts)
        return text

    # ── CommandPy ──
    @property
    def Name(self):
        return self._name

    @Name.setter
    def Name(self, v):
        object.__setattr__(self, "_name", str(v).upper())

    @property
    def Parameters(self):
        if not self._cache:
            object.__setattr__(self, "_cache", {k: self._params[k] for k in sorted(self._params)})
        return self._cache

    @Parameters.setter
    def Parameters(self, d):
        params = {}
        for k, v in d.items():
            if not isinstance(k, str):
                raise TypeError("The dictionary can only contain string keys")
            params[k.upper()] = _num(v)
        object.__setattr__(self, "_params", params)
        object.__setattr__(self, "_cache", {})

    @property
    def Annotations(self):
        return dict(sorted(self._ann.items()))

    @Annotations.setter
    def Annotations(self, d):
        self._ann.clear()
        for k, v in d.items():
            if isinstance(v, str):
                self._ann[k] = v
            elif isinstance(v, (int, float)):
                self._ann[k] = float(v)
            else:
                raise TypeError("Annotation values must be strings or numbers")

    def addAnnotations(self, a):
        if isinstance(a, dict):
            for k, v in a.items():
                if not isinstance(k, str) or not isinstance(v, str):
                    raise TypeError("Dictionary keys and values must be strings")
                self._ann[k] = v
        elif isinstance(a, str):
            self._set_annotations(a)
        else:
            raise TypeError("Argument must be a dictionary or string")
        return self

    @property
    def Placement(self):
        return self._placement()

    @Placement.setter
    def Placement(self, pl):
        if not isinstance(pl, Placement):
            raise TypeError("Argument must be a placement")
        self._set_from_placement(pl)
        object.__setattr__(self, "_cache", None)

    def toGCode(self):
        return self._to_gcode()

    def setFromGCode(self, s):
        try:
            self._set_from_gcode(s)
        except BadFormatError as e:
            raise ValueError(str(e)) from None
        object.__setattr__(self, "_cache", None)

    def transform(self, pl):
        p = self._placement().multiply(pl)
        a, b, c = p._rot.getYawPitchRoll()
        out = Command()
        object.__setattr__(out, "_name", self._name)
        for k, v in self._params.items():
            v = {"X": p._pos.x, "Y": p._pos.y, "Z": p._pos.z, "A": a, "B": b, "C": c}.get(k, v)
            out._params[k] = v
        out._ann.update(self._ann)
        object.__setattr__(self, "_cache", None)
        return out

    def __getattr__(self, name):
        if len(name) == 1 and name.isalpha():
            return self._params.get(name.upper())
        raise AttributeError(f"'Path.Command' object has no attribute '{name}'")

    def __setattr__(self, name, value):
        if name in ("Name", "Parameters", "Annotations", "Placement"):
            getattr(type(self), name).fset(self, value)
            return
        if len(name) == 1 and name.isalpha():
            if isinstance(value, (int, float)):
                self._params[name.upper()] = float(value)
                object.__setattr__(self, "_cache", None)
            return
        raise AttributeError(f"'Path.Command' object has no attribute '{name}'")

    def __repr__(self):
        return "Command " + self._name + " [" + "".join(f" {k}:{_g5(v)}" for k, v in sorted(self._params.items())) + " ]"

    def __copy__(self):
        c = Command()
        object.__setattr__(c, "_name", self._name)
        object.__setattr__(c, "_params", dict(self._params))
        object.__setattr__(c, "_ann", dict(self._ann))
        return c

    __deepcopy__ = lambda self, memo: self.__copy__()  # noqa: E731

    def __reduce__(self):
        return (_restore_cmd, (self._name, dict(self._params), dict(self._ann)))

    def _copy(self):
        return self.__copy__()


def _restore_cmd(name, params, ann):
    c = Command()
    object.__setattr__(c, "_name", name)
    object.__setattr__(c, "_params", params)
    object.__setattr__(c, "_ann", ann)
    return c


def _g5(v):
    """std::stringstream with precision(5): the shortest of fixed and scientific with 5 significant digits."""
    s = f"{v:.5g}"
    if "e" in s:
        m, e = s.split("e")
        e = int(e)
        s = f"{m}e{'-' if e < 0 else '+'}{abs(e):02d}"
    return s


def _atof(s):
    """std::atof: the longest numeric prefix, 0 when none."""
    import re
    m = re.match(r"\s*[-+]?(\d+\.?\d*|\.\d+)([eE][-+]?\d+)?", s)
    return float(m.group(0)) if m else 0.0


# ─── Toolpath ───────────────────────────────────────────────────────────────────────────────────────────────────────

_RAPID = ("G0", "G00")
_LINEAR = ("G0", "G00", "G1", "G01")
_ARC = ("G2", "G02", "G3", "G03")


def _next_position(cmd, last, absolute):
    if absolute:
        return cmd._placement(last)._pos
    return last + cmd._placement()._pos


def _arc_length(cmd, last, nxt, absolute_center):
    c = cmd._params
    center = Vector(c.get("I", 0.0), c.get("J", 0.0), c.get("K", 0.0))
    if not absolute_center:
        center = last + center
    n0, l0, c0 = Vector(nxt.x, nxt.y, 0.0), Vector(last.x, last.y, 0.0), Vector(center.x, center.y, 0.0)
    radius = (l0 - c0).Length
    angle = (n0 - c0).getAngle(l0 - c0)
    normal = (l0 - c0).cross(n0 - c0)
    if normal.z < 0.0:
        if cmd._name in ("G3", "G03"):
            angle = math.pi * 2 - angle
    elif normal.z > 0.0:
        if cmd._name in ("G2", "G02"):
            angle = math.pi * 2 - angle
    elif angle == 0.0:
        angle = math.pi * 2
    return angle * radius


class Path:
    def __init__(self, arg=None):
        self._cmds = []
        self._center = Vector()
        if arg is None:
            return
        if isinstance(arg, Path):
            self._cmds = [c._copy() for c in arg._cmds]
            self._center = Vector(arg._center)
            return
        if isinstance(arg, list):
            for c in arg:
                if not isinstance(c, Command):
                    raise TypeError("The list must contain only Path Commands")
                self._cmds.append(c._copy())
            return
        if isinstance(arg, str):
            self._set_from_gcode(arg)
            return
        raise TypeError("Argument must be a list of commands or a gcode string")

    @property
    def Commands(self):
        return [c._copy() for c in self._cmds]

    @Commands.setter
    def Commands(self, lst):
        cmds = []
        for c in lst:
            if not isinstance(c, Command):
                raise TypeError("The list can only contain Path Commands")
            cmds.append(c._copy())
        self._cmds = cmds

    @property
    def Size(self):
        return len(self._cmds)

    @property
    def Center(self):
        return Vector(self._center)

    @Center.setter
    def Center(self, v):
        self._center = Vector(v)

    def copy(self):
        return Path(self)

    def addCommands(self, o):
        if isinstance(o, Command):
            self._cmds.append(o._copy())
        elif isinstance(o, list):
            for c in o:
                if isinstance(c, Command):
                    self._cmds.append(c._copy())
        else:
            raise TypeError("Wrong parameters - command or list of commands expected")
        return Path(self)

    def insertCommand(self, cmd, pos=-1):
        if pos == -1:
            self._cmds.append(cmd._copy())
        elif 0 <= pos <= len(self._cmds):
            self._cmds.insert(pos, cmd._copy())
        else:
            raise IndexError("Index not in range")
        return Path(self)

    def deleteCommand(self, pos=-1):
        if pos == -1:
            pos = len(self._cmds) - 1
        if 0 <= pos < len(self._cmds):
            del self._cmds[pos]
        else:
            raise IndexError("Index not in range")
        return Path(self)

    @property
    def Length(self):
        if not self._cmds:
            return 0.0
        total, last = 0.0, Vector()
        absolute, abs_center = True, False
        for c in self._cmds:
            n = c._name
            nxt = _next_position(c, last, absolute)
            if n in _LINEAR:
                total += (nxt - last).Length
                last = nxt
            elif n in _ARC:
                total += _arc_length(c, last, nxt, abs_center)
                last = nxt
            elif n == "G90":
                absolute = True
            elif n == "G91":
                absolute = False
            elif n == "G90.1":
                abs_center = True
            elif n == "G91.1":
                abs_center = False
        return total

    def getCycleTime(self, h_feed, v_feed, rapid):
        h_feed, v_feed, rapid = float(h_feed), float(v_feed), float(rapid)
        if h_feed == 0 or v_feed == 0:
            return 0.0
        if rapid == 0:
            rapid = h_feed
        if not self._cmds:
            return 0.0
        time, f0, f1, last = 0.0, rapid, h_feed, Vector()
        absolute, abs_center = True, False
        for c in self._cmds:
            n = c._name
            fc = c._p("F")
            ln, feed = 0.0, h_feed
            nxt = _next_position(c, last, absolute)
            if n in _RAPID:
                ln = (nxt - last).Length
                if fc:
                    f0 = fc
                feed = f0
            elif n in ("G1", "G01"):
                ln = (nxt - last).Length
                if fc:
                    f1 = fc
                feed = f1
            elif n in _ARC:
                ln = _arc_length(c, last, nxt, abs_center)
                if fc:
                    f1 = fc
                feed = f1
            elif n == "G90":
                absolute = True
            elif n == "G91":
                absolute = False
            elif n == "G90.1":
                abs_center = True
            elif n == "G91.1":
                abs_center = False
            time += ln / feed
            last = nxt
        return time

    @property
    def BoundBox(self):
        from ._fc_walker import bound_box
        return bound_box(self)

    def toGCode(self):
        return "".join(c._to_gcode() + "\n" for c in self._cmds)

    def setFromGCode(self, s):
        self._set_from_gcode(s)

    def _set_from_gcode(self, s):
        self._cmds = []
        inches = [False]

        def add(text):
            c = Command()
            c._set_from_gcode(text)
            if c._name == "G20":
                inches[0] = True
            elif c._name == "G21":
                inches[0] = False
            else:
                if inches[0]:
                    for k in list(c._params):
                        if k[0] in "XYZIJRQF":
                            c._params[k] *= 25.4
                self._cmds.append(c)

        def find_of(chars, start):
            for i in range(start, len(s)):
                if s[i] in chars:
                    return i
            return -1
        mode, last = "command", -1
        found = find_of("(gGmM", 0)
        while found != -1:
            if s[found] == "(":
                if last > -1 and mode == "command":
                    add(s[last:found])
                mode = "comment"
                last = found
                found = find_of(")", found + 1)
            elif s[found] == ")":
                add(s[last:found + 1])
                last = -1
                found = find_of("(gGmM", found + 1)
                mode = "command"
            elif mode == "command":
                if last > -1:
                    add(s[last:found])
                last = found
                found = find_of("(gGmM", found + 1)
        if last > -1 and mode == "command":
            add(s[last:])

    def __repr__(self):
        return f"Path [ size:{len(self._cmds)} length:{self.Length:g} ]"

    def __reduce__(self):
        return (_restore_path, ([c.__reduce__()[1] for c in self._cmds],))


def _restore_path(cmds):
    p = Path()
    p._cmds = [_restore_cmd(*c) for c in cmds]
    return p
