# SPDX-License-Identifier: LGPL-2.1-or-later
#
# This file is not MIT. It re-expresses FreeCAD's Base types and keeps FreeCAD's licence, the GNU Lesser General Public
# License, version 2.1 or (at your option) any later version; the text is in ../../ui/LICENSE.
#
#   Derived from: src/Base/Vector3D.cpp, VectorPyImp.cpp (Copyright (c) 2005 Imetric 3D GmbH, Juergen Riegel),
#                 src/Base/Rotation.cpp, RotationPyImp.cpp (Copyright (c) 2005 Werner Mayer),
#                 src/Base/Placement.cpp, PlacementPyImp.cpp (Copyright (c) 2006 Juergen Riegel),
#                 src/Base/Matrix.cpp, MatrixPyImp.cpp (Copyright (c) 2005 Imetric 3D GmbH),
#                 src/Base/BoundBox.h, BoundBoxPyImp.cpp (Copyright (c) 2005 Imetric 3D GmbH)
#                 FreeCAD (https://github.com/FreeCAD/FreeCAD), commit 3160daf1e2b62b0472854da4848255c6b3ad554c
#
# See ../../NOTICE.
"""FreeCAD's Base types for the CAM workbench's Python (docs/EDITING_PLAN.md, "CAM in a project"): Vector, Rotation,
Placement, Matrix and BoundBox with the methods and the arithmetic of their C++ classes, so that FreeCAD's CAM code
computes the same numbers here as in FreeCAD."""
from __future__ import annotations

import math
import sys

EPS = sys.float_info.epsilon        # Vector3d::epsilon(), numeric_limits<double>::epsilon()
CONFUSION = 1e-7                    # Base::Precision::Confusion()


class FreeCADError(RuntimeError):
    """Base.FreeCADError (PyExc_FC_GeneralError)."""


def _num(v):
    if isinstance(v, bool):
        return float(v)
    if hasattr(v, "Value") and not isinstance(v, Vector):     # a Quantity
        return float(v.Value)
    return float(v)


class Vector:
    __slots__ = ("x", "y", "z")

    def __init__(self, *args):
        if not args:
            self.x = self.y = self.z = 0.0
            return
        if len(args) == 1:
            a = args[0]
            if isinstance(a, Vector):
                self.x, self.y, self.z = a.x, a.y, a.z
                return
            if hasattr(a, "X") and hasattr(a, "Y") and hasattr(a, "Z") and not isinstance(a, (tuple, list)):
                self.x, self.y, self.z = float(a.X()), float(a.Y()), float(a.Z())      # gp_Pnt / gp_Vec / gp_Dir
                return
            if isinstance(a, (tuple, list)):
                if len(a) != 3:
                    raise TypeError("Either three floats, tuple or Vector expected")
                self.x, self.y, self.z = (_num(v) for v in a)
                return
            self.x, self.y, self.z = _num(a), 0.0, 0.0
            return
        if len(args) > 3:
            raise TypeError("Either three floats, tuple or Vector expected")
        vals = [_num(v) for v in args] + [0.0] * (3 - len(args))
        self.x, self.y, self.z = vals

    # ── sequence ──
    def __len__(self):
        return 3

    def __getitem__(self, i):
        if isinstance(i, slice):
            return [self.x, self.y, self.z][i]
        if i < 0:
            i += 3
        if i == 0:
            return self.x
        if i == 1:
            return self.y
        if i == 2:
            return self.z
        raise IndexError("index out of range")

    def __setitem__(self, i, v):
        if i < 0:
            i += 3
        if i not in (0, 1, 2):
            raise IndexError("index out of range")
        setattr(self, "xyz"[i], float(v))

    def __iter__(self):
        return iter((self.x, self.y, self.z))

    # ── arithmetic (VectorPy's number handlers) ──
    def __add__(self, o):
        if not isinstance(o, Vector):
            raise TypeError("Second arg must be Vector")
        return Vector(self.x + o.x, self.y + o.y, self.z + o.z)

    def __sub__(self, o):
        if not isinstance(o, Vector):
            raise TypeError("Second arg must be Vector")
        return Vector(self.x - o.x, self.y - o.y, self.z - o.z)

    def __mul__(self, o):
        if isinstance(o, Vector):
            return (self.x * o.x) + (self.y * o.y) + (self.z * o.z)
        if isinstance(o, (int, float)) or hasattr(o, "__float__"):
            b = float(o)
            return Vector(self.x * b, self.y * b, self.z * b)
        return NotImplemented

    def __rmul__(self, o):
        if isinstance(o, (int, float)) or hasattr(o, "__float__"):
            b = float(o)
            return Vector(self.x * b, self.y * b, self.z * b)
        return NotImplemented

    def __truediv__(self, o):
        if isinstance(o, Vector):
            raise TypeError("unsupported operand type(s) for /: 'Base.Vector' and 'Base.Vector'")
        d = float(o)
        if d == 0.0:
            raise ZeroDivisionError("'Base.Vector' division by zero")
        return Vector(self.x / d, self.y / d, self.z / d)

    def __mod__(self, o):
        return self.cross(o)

    def __neg__(self):
        return Vector(-self.x, -self.y, -self.z)

    def __pos__(self):
        return Vector(self)

    def __abs__(self):
        return Vector(abs(self.x), abs(self.y), abs(self.z))

    def __bool__(self):
        return True

    def __eq__(self, o):
        if not isinstance(o, Vector):
            return NotImplemented
        return abs(self.x - o.x) <= EPS and abs(self.y - o.y) <= EPS and abs(self.z - o.z) <= EPS

    def __ne__(self, o):
        r = self.__eq__(o)
        return r if r is NotImplemented else not r

    __hash__ = None

    def __repr__(self):
        return f"Vector ({self.x!r}, {self.y!r}, {self.z!r})"

    __str__ = __repr__

    def __copy__(self):
        return Vector(self)

    def __deepcopy__(self, memo):
        return Vector(self)

    def __reduce__(self):
        return (Vector, (self.x, self.y, self.z))

    # ── VectorPy's methods ──
    def add(self, o):
        return self + o

    def sub(self, o):
        return self - o

    def negative(self):
        return -self

    def dot(self, o):
        return (self.x * o.x) + (self.y * o.y) + (self.z * o.z)

    def cross(self, o):
        return Vector((self.y * o.z) - (self.z * o.y), (self.z * o.x) - (self.x * o.z), (self.x * o.y) - (self.y * o.x))

    def multiply(self, f):
        f = float(f)
        self.x *= f
        self.y *= f
        self.z *= f
        return self

    def scale(self, fx, fy, fz):
        self.x *= float(fx)
        self.y *= float(fy)
        self.z *= float(fz)
        return self

    def _len(self):
        return math.sqrt((self.x * self.x) + (self.y * self.y) + (self.z * self.z))

    @property
    def Length(self):
        return self._len()

    @Length.setter
    def Length(self, v):
        n = self._len()
        if n < EPS:
            raise RuntimeError("Cannot set length of null vector")
        val = float(v) / n
        self.x *= val
        self.y *= val
        self.z *= val

    def _normalize(self):
        n = self._len()
        if n != 0.0 and n != 1.0:
            self.x /= n
            self.y /= n
            self.z /= n
        return self

    def normalize(self):
        if self._len() < EPS:
            raise FreeCADError("Cannot normalize null vector")
        return self._normalize()

    def getAngle(self, o):
        l1, l2 = self._len(), o._len()
        if l1 <= EPS or l2 <= EPS:
            return float("nan")
        d = self.dot(o)
        d /= l1
        d /= l2
        if d <= -1.0:
            return math.pi
        if d >= 1.0:
            return 0.0
        return math.acos(d)

    def isEqual(self, o, tol):
        return (self - o)._len() <= tol

    def isParallel(self, o, tol):
        a = self.getAngle(o)
        if math.isnan(a):
            return False
        return a <= tol or math.pi - a <= tol

    def isNormal(self, o, tol):
        a = self.getAngle(o)
        if math.isnan(a):
            return False
        return abs(math.pi / 2.0 - a) <= tol

    def isOnLineSegment(self, start, end):
        ab, ac = end - start, self - start
        cp, dp = ab.cross(ac), ab.dot(ac)
        if cp._len() > EPS:
            return False
        if dp < 0:
            return False
        if dp > ab.dot(ab):
            return False
        return True

    def distanceToPoint(self, o):
        return (self - o)._len()

    def distanceToLine(self, base, d):
        return abs(d.cross(self - base)._len() / d._len())

    def distanceToLineSegment(self, p1, p2):
        d = p2 - p1
        len2 = d.dot(d)
        if len2 == 0:
            return Vector(p1)
        px = self - p1
        t = min(max(px.dot(d) / len2, 0.0), 1.0)
        return d * t - px

    def distanceToPlane(self, base, norm):
        return (self - base).dot(norm) / norm._len()

    def projectToLine(self, point, line):
        r = line * ((point * line) / line.dot(line)) - point
        self.x, self.y, self.z = r.x, r.y, r.z
        return self

    def projectToPlane(self, base, norm):
        t = Vector(norm)
        t.multiply(((self - base) * t) / t.dot(t))
        r = self - t
        self.x, self.y, self.z = r.x, r.y, r.z
        return self

    def to_gp_Pnt(self):
        from OCP.gp import gp_Pnt
        return gp_Pnt(self.x, self.y, self.z)


def vec(v) -> Vector:
    return v if isinstance(v, Vector) else Vector(v)


# ─── Matrix ─────────────────────────────────────────────────────────────────────────────────────────────────────────

class Matrix:
    """Base::Matrix4D, row major: A11..A44."""

    def __init__(self, *args):
        self.m = [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0], [0.0, 0.0, 0.0, 1.0]]
        if len(args) == 1 and isinstance(args[0], Matrix):
            self.m = [r[:] for r in args[0].m]
        elif len(args) == 16:
            self.m = [[float(args[r * 4 + c]) for c in range(4)] for r in range(4)]
        elif args:
            vals = [float(a) for a in args] + [None] * (16 - len(args))
            ident = [1.0 if r == c else 0.0 for r in range(4) for c in range(4)]
            self.m = [[vals[r * 4 + c] if vals[r * 4 + c] is not None else ident[r * 4 + c] for c in range(4)]
                      for r in range(4)]

    def __getattr__(self, name):
        if len(name) == 3 and name[0] == "A" and name[1:].isdigit():
            return self.m[int(name[1]) - 1][int(name[2]) - 1]
        raise AttributeError(name)

    def __setattr__(self, name, v):
        if len(name) == 3 and name[0] == "A" and name[1:].isdigit():
            self.m[int(name[1]) - 1][int(name[2]) - 1] = float(v)
        else:
            object.__setattr__(self, name, v)

    def multVec(self, v):
        m = self.m
        return Vector(m[0][0] * v.x + m[0][1] * v.y + m[0][2] * v.z + m[0][3],
                      m[1][0] * v.x + m[1][1] * v.y + m[1][2] * v.z + m[1][3],
                      m[2][0] * v.x + m[2][1] * v.y + m[2][2] * v.z + m[2][3])

    def multiply(self, o):
        if isinstance(o, Vector):
            return self.multVec(o)
        r = Matrix()
        r.m = [[sum(self.m[i][k] * o.m[k][j] for k in range(4)) for j in range(4)] for i in range(4)]
        return r

    __mul__ = multiply

    def transposed(self):
        r = Matrix()
        r.m = [[self.m[j][i] for j in range(4)] for i in range(4)]
        return r

    def move(self, v):
        v = vec(v)
        self.m[0][3] += v.x
        self.m[1][3] += v.y
        self.m[2][3] += v.z

    def isUnity(self, tol=0.0):
        return all(abs(self.m[i][j] - (1.0 if i == j else 0.0)) <= tol for i in range(4) for j in range(4))

    def __repr__(self):
        return "Matrix (" + ",".join(repr(x) for r in self.m for x in r) + ")"


# ─── Rotation ───────────────────────────────────────────────────────────────────────────────────────────────────────

class Rotation:
    __slots__ = ("quat", "_axis", "_angle")

    def __init__(self, *args):
        self.quat = [0.0, 0.0, 0.0, 1.0]
        self._axis = Vector(0.0, 0.0, 1.0)
        self._angle = 0.0
        if not args:
            return
        if len(args) == 1:
            a = args[0]
            if isinstance(a, Rotation):
                self.quat, self._axis, self._angle = a.quat[:], Vector(a._axis), a._angle
                return
            if isinstance(a, Matrix):
                self._set_matrix(a)
                return
            if isinstance(a, (tuple, list)) and len(a) == 4:
                self._set_q(*[float(x) for x in a])
                return
            raise TypeError("Rotation constructor: unsupported argument")
        if len(args) == 2 and isinstance(args[0], Vector) and isinstance(args[1], Vector):
            self._set_from_to(args[0], args[1])
            return
        if len(args) == 2:
            axis, angle = args
            self._axis = Vector(0.0, 0.0, 1.0)
            self._set_axis_angle(vec(axis), math.radians(_num(angle)))
            return
        if len(args) == 3 and all(isinstance(a, (int, float)) for a in args):
            self._set_ypr(*[float(a) for a in args])
            return
        if len(args) == 3 and isinstance(args[0], str):
            raise TypeError("Euler sequences are not supported")
        if len(args) == 4:
            self._set_q(*[float(a) for a in args])
            return
        raise TypeError("Rotation constructor: unsupported arguments")

    # ── Rotation.cpp ──
    def _normalize(self):
        q = self.quat
        n = math.sqrt(q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3])
        if n > 0.0:
            self.quat = [q[0] / n, q[1] / n, q[2] / n, q[3] / n]

    def _evaluate_vector(self):
        q = self.quat
        if -1.0 < q[3] < 1.0:
            ang = math.acos(q[3]) * 2.0
            scale = math.sin(ang / 2.0)
            n = self._axis._len()
            if n < EPS:
                n = 1
            self._axis = Vector(q[0] * n / scale, q[1] * n / scale, q[2] * n / scale)
            self._angle = ang
        else:
            self._axis = Vector(0.0, 0.0, 1.0)
            self._angle = 0.0

    def _set_q(self, q0, q1, q2, q3):
        self.quat = [q0, q1, q2, q3]
        self._normalize()
        self._evaluate_vector()

    def _set_axis_angle(self, axis, angle):
        self._angle = angle
        a = angle - math.floor(angle / (2.0 * math.pi)) * (2.0 * math.pi)
        w = math.cos(a / 2.0)
        norm = Vector(axis)._normalize()
        if norm._len() > 0.5:
            self._axis = Vector(axis)
        else:
            norm = Vector(self._axis)._normalize()
        s = math.sin(a / 2.0)
        self.quat = [norm.x * s, norm.y * s, norm.z * s, w]

    def _set_from_to(self, a, b):
        u = Vector(a)._normalize()
        v = Vector(b)._normalize()
        d = u * v
        w = u.cross(v)
        if w._len() == 0.0:
            if d > 0.0:
                self._set_q(0.0, 0.0, 0.0, 1.0)
            else:
                t = u.cross(Vector(1.0, 0.0, 0.0))
                if t._len() < EPS:
                    t = u.cross(Vector(0.0, 1.0, 0.0))
                self._set_q(t.x, t.y, t.z, 0.0)
        else:
            self._set_axis_angle(w, math.acos(d))

    def _set_ypr(self, y, p, r):
        y, p, r = math.radians(y), math.radians(p), math.radians(r)
        c1, s1 = math.cos(y / 2.0), math.sin(y / 2.0)
        c2, s2 = math.cos(p / 2.0), math.sin(p / 2.0)
        c3, s3 = math.cos(r / 2.0), math.sin(r / 2.0)
        self._set_q(c1 * c2 * s3 - s1 * s2 * c3, c1 * s2 * c3 + s1 * c2 * s3, s1 * c2 * c3 - c1 * s2 * s3,
                    c1 * c2 * c3 + s1 * s2 * s3)

    def _set_matrix(self, m):
        mc = [[m.m[r][c] for c in range(3)] for r in range(3)]
        # Matrix4D::decompose()[2]: the rotation part (scale and shear removed); a pure rotation stays as it is
        cols = [[mc[0][c], mc[1][c], mc[2][c]] for c in range(3)]
        for c in range(3):
            n = math.sqrt(sum(x * x for x in cols[c]))
            if n > 0:
                for r in range(3):
                    mc[r][c] /= n
        q = [0.0, 0.0, 0.0, 0.0]
        trace = mc[0][0] + mc[1][1] + mc[2][2]
        if trace > 0.0:
            s = math.sqrt(1.0 + trace)
            q[3] = 0.5 * s
            s = 0.5 / s
            q[0] = (mc[2][1] - mc[1][2]) * s
            q[1] = (mc[0][2] - mc[2][0]) * s
            q[2] = (mc[1][0] - mc[0][1]) * s
        else:
            i = 0
            if mc[1][1] > mc[0][0]:
                i = 1
            if mc[2][2] > mc[i][i]:
                i = 2
            j, k = (i + 1) % 3, (i + 2) % 3
            s = math.sqrt((mc[i][i] - (mc[j][j] + mc[k][k])) + 1.0)
            q[i] = s * 0.5
            s = 0.5 / s
            q[3] = (mc[k][j] - mc[j][k]) * s
            q[j] = (mc[j][i] + mc[i][j]) * s
            q[k] = (mc[k][i] + mc[i][k]) * s
        self.quat = q
        self._evaluate_vector()

    def _mult_right(self, o):
        x0, y0, z0, w0 = self.quat
        x1, y1, z1, w1 = o.quat
        self._set_q(w0 * x1 + x0 * w1 + y0 * z1 - z0 * y1, w0 * y1 - x0 * z1 + y0 * w1 + z0 * x1,
                    w0 * z1 + x0 * y1 - y0 * x1 + z0 * w1, w0 * w1 - x0 * x1 - y0 * y1 - z0 * z1)
        return self

    def _mult_vec(self, v):
        x, y, z, w = self.quat
        x2, y2, z2, w2 = x * x, y * y, z * z, w * w
        return Vector((x2 + w2 - y2 - z2) * v.x + 2.0 * (x * y - z * w) * v.y + 2.0 * (x * z + y * w) * v.z,
                      2.0 * (x * y + z * w) * v.x + (w2 - x2 + y2 - z2) * v.y + 2.0 * (y * z - x * w) * v.z,
                      2.0 * (x * z - y * w) * v.x + 2.0 * (x * w + y * z) * v.y + (w2 - x2 - y2 + z2) * v.z)

    def _matrix(self):
        q = self.quat
        n = math.sqrt(q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3])
        x, y, z, w = q[0] / n, q[1] / n, q[2] / n, q[3] / n
        m = Matrix()
        m.m = [[1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w), 0.0],
               [2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w), 0.0],
               [2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y), 0.0],
               [0.0, 0.0, 0.0, 1.0]]
        return m

    # ── RotationPy ──
    @property
    def Q(self):
        return tuple(self.quat)

    @Q.setter
    def Q(self, q):
        self._set_q(*[float(x) for x in q])

    @property
    def Axis(self):
        return Vector(self._axis)._normalize()

    @Axis.setter
    def Axis(self, v):
        self._set_axis_angle(vec(v), self._angle)

    @property
    def RawAxis(self):
        return Vector(self._axis)

    @property
    def Angle(self):
        return self._angle

    @Angle.setter
    def Angle(self, a):
        self._set_axis_angle(self._axis, float(a))

    def multVec(self, v):
        return self._mult_vec(vec(v))

    def multiply(self, o):
        r = Rotation(self)
        return r._mult_right(o)

    __mul__ = multiply

    def inverted(self):
        r = Rotation()
        r.quat = [-self.quat[0], -self.quat[1], -self.quat[2], self.quat[3]]
        r._axis = -self._axis
        r._angle = self._angle
        return r

    def invert(self):
        self.quat = [-self.quat[0], -self.quat[1], -self.quat[2], self.quat[3]]
        self._axis = -self._axis

    def isIdentity(self, tol=None):
        q = self.quat
        if tol is None:
            return q[0] == 0.0 and q[1] == 0.0 and q[2] == 0.0 and (q[3] == 1.0 or q[3] == -1.0)
        return abs(q[3]) >= 1.0 - tol / 2

    def isNull(self):
        return all(x == 0.0 for x in self.quat)

    def isSame(self, o, tol=None):
        if tol is None:
            return self.quat == o.quat or self.quat == [-x for x in o.quat]
        d = sum(a * b for a, b in zip(self.quat, o.quat))
        return abs(d) >= 1.0 - tol / 2

    def getYawPitchRoll(self):
        q = self.quat
        q00, q11, q22, q33 = q[0] * q[0], q[1] * q[1], q[2] * q[2], q[3] * q[3]
        q01, q02, q03 = q[0] * q[1], q[0] * q[2], q[0] * q[3]
        q12, q13, q23 = q[1] * q[2], q[1] * q[3], q[2] * q[3]
        qd2 = 2.0 * (q13 - q02)
        tol = 16 * EPS
        if abs(qd2 - 1.0) <= tol:
            y, p, r = 0.0, math.pi / 2.0, 2.0 * math.atan2(q[0], q[3])
        elif abs(qd2 + 1.0) <= tol:
            y, p, r = 0.0, -math.pi / 2.0, 2.0 * math.atan2(q[0], q[3])
        else:
            y = math.atan2(2.0 * (q01 + q23), (q00 + q33) - (q11 + q22))
            p = math.pi / 2.0 if qd2 > 1.0 else (-math.pi / 2.0 if qd2 < -1.0 else math.asin(qd2))
            r = math.atan2(2.0 * (q12 + q03), (q22 + q33) - (q00 + q11))
        return (math.degrees(y), math.degrees(p), math.degrees(r))

    def toEuler(self):
        return self.getYawPitchRoll()

    def toMatrix(self):
        return self._matrix()

    def __eq__(self, o):
        return isinstance(o, Rotation) and self.isSame(o)

    __hash__ = None

    def __repr__(self):
        return f"Rotation ({self.quat[0]!r}, {self.quat[1]!r}, {self.quat[2]!r}, {self.quat[3]!r})"

    def __copy__(self):
        return Rotation(self)

    def __deepcopy__(self, memo):
        return Rotation(self)


# ─── Placement ──────────────────────────────────────────────────────────────────────────────────────────────────────

class Placement:
    __slots__ = ("_pos", "_rot")

    def __init__(self, *args):
        self._pos = Vector()
        self._rot = Rotation()
        if not args:
            return
        if len(args) == 1:
            a = args[0]
            if isinstance(a, Placement):
                self._pos, self._rot = Vector(a._pos), Rotation(a._rot)
                return
            if isinstance(a, Matrix):
                self._rot = Rotation(a)
                self._pos = Vector(a.m[0][3], a.m[1][3], a.m[2][3])
                return
            raise TypeError("Placement constructor: unsupported argument")
        base = vec(args[0])
        if len(args) == 2:
            self._pos, self._rot = Vector(base), Rotation(args[1])
            return
        if len(args) == 3 and isinstance(args[1], Rotation):        # (base, rotation, center)
            rot, center = args[1], vec(args[2])
            self._rot = Rotation(rot)
            self._pos = base + center - rot.multVec(center)
            return
        if len(args) == 3:                                            # (base, axis, angle)
            self._pos, self._rot = Vector(base), Rotation(vec(args[1]), args[2])
            return
        raise TypeError("Placement constructor: unsupported arguments")

    @property
    def Base(self):
        return Vector(self._pos)

    @Base.setter
    def Base(self, v):
        self._pos = Vector(vec(v))

    @property
    def Rotation(self):
        return Rotation(self._rot)

    @Rotation.setter
    def Rotation(self, r):
        self._rot = Rotation(r) if isinstance(r, Rotation) else Rotation(*r)

    @property
    def Matrix(self):
        return self.toMatrix()

    def toMatrix(self):
        m = self._rot._matrix()
        m.m[0][3], m.m[1][3], m.m[2][3] = self._pos.x, self._pos.y, self._pos.z
        return m

    def multVec(self, v):
        return self._rot._mult_vec(vec(v)) + self._pos

    def multiply(self, o):
        r = Placement()
        r._pos = self._rot._mult_vec(o._pos) + self._pos
        r._rot = Rotation(self._rot)._mult_right(o._rot)
        return r

    __mul__ = multiply

    def inverse(self):
        r = Placement()
        r._rot = self._rot.inverted()
        r._pos = -r._rot._mult_vec(self._pos)
        return r

    def isIdentity(self, tol=None):
        if tol is None:
            return self._pos.x == 0.0 and self._pos.y == 0.0 and self._pos.z == 0.0 and self._rot.isIdentity()
        return self._pos._len() <= tol and self._rot.isIdentity(tol)

    def isNull(self):
        return self._pos == Vector() and self._rot.isNull()

    def copy(self):
        return Placement(self)

    def move(self, v):
        self._pos = self._pos + vec(v)

    def translate(self, v):
        self.move(v)

    def rotate(self, center, axis, angle, comp=False):
        rot = Rotation(vec(axis), angle)
        c = vec(center)
        p = Placement(c - rot.multVec(c), rot)
        res = p.multiply(self) if not comp else self.multiply(p)
        self._pos, self._rot = res._pos, res._rot

    def __eq__(self, o):
        return isinstance(o, Placement) and self._pos == o._pos and self._rot == o._rot

    __hash__ = None

    def __repr__(self):
        a = self._rot
        return f"Placement [Pos=({self._pos.x!r},{self._pos.y!r},{self._pos.z!r}), Yaw-Pitch-Roll={a.getYawPitchRoll()}]"

    def __copy__(self):
        return Placement(self)

    def __deepcopy__(self, memo):
        return Placement(self)


# ─── BoundBox ───────────────────────────────────────────────────────────────────────────────────────────────────────

class BoundBox:
    def __init__(self, *args):
        big = sys.float_info.max
        self.XMin, self.YMin, self.ZMin = big, big, big
        self.XMax, self.YMax, self.ZMax = -big, -big, -big
        if len(args) == 1 and isinstance(args[0], BoundBox):
            o = args[0]
            self.XMin, self.YMin, self.ZMin, self.XMax, self.YMax, self.ZMax = (
                o.XMin, o.YMin, o.ZMin, o.XMax, o.YMax, o.ZMax)
        elif len(args) == 6:
            (self.XMin, self.YMin, self.ZMin, self.XMax, self.YMax, self.ZMax) = (float(a) for a in args)
        elif len(args) == 2 and all(isinstance(a, Vector) for a in args):
            a, b = args
            self.XMin, self.YMin, self.ZMin = min(a.x, b.x), min(a.y, b.y), min(a.z, b.z)
            self.XMax, self.YMax, self.ZMax = max(a.x, b.x), max(a.y, b.y), max(a.z, b.z)
        elif args:
            raise TypeError("Either six floats, two instances of Vector/Tuple or instance of BoundBox expected")

    def isValid(self):
        return self.XMin <= self.XMax and self.YMin <= self.YMax and self.ZMin <= self.ZMax

    def _check(self):
        if not self.isValid():
            raise FloatingPointError("Invalid bounding box")

    def add(self, *args):
        if len(args) == 1 and isinstance(args[0], BoundBox):
            o = args[0]
            self.XMin, self.XMax = min(self.XMin, o.XMin), max(self.XMax, o.XMax)
            self.YMin, self.YMax = min(self.YMin, o.YMin), max(self.YMax, o.YMax)
            self.ZMin, self.ZMax = min(self.ZMin, o.ZMin), max(self.ZMax, o.ZMax)
            return
        v = Vector(*args) if len(args) == 3 else vec(args[0])
        self.XMin, self.XMax = min(self.XMin, v.x), max(self.XMax, v.x)
        self.YMin, self.YMax = min(self.YMin, v.y), max(self.YMax, v.y)
        self.ZMin, self.ZMax = min(self.ZMin, v.z), max(self.ZMax, v.z)

    def intersect(self, *args):
        self._check()
        if len(args) == 2:
            raise NotImplementedError("BoundBox.intersect(Vector, Vector)")
        o = args[0]
        if not o.isValid():
            raise FloatingPointError("Invalid bounding box argument")
        if o.XMax < self.XMin or o.XMin > self.XMax:
            return False
        if o.YMax < self.YMin or o.YMin > self.YMax:
            return False
        if o.ZMax < self.ZMin or o.ZMin > self.ZMax:
            return False
        return True

    def intersected(self, o):
        r = BoundBox()
        r.XMin, r.YMin, r.ZMin = max(self.XMin, o.XMin), max(self.YMin, o.YMin), max(self.ZMin, o.ZMin)
        r.XMax, r.YMax, r.ZMax = min(self.XMax, o.XMax), min(self.YMax, o.YMax), min(self.ZMax, o.ZMax)
        return r

    def united(self, o):
        r = BoundBox(self)
        r.add(o)
        return r

    def enlarge(self, s):
        s = float(s)
        self.XMin -= s
        self.YMin -= s
        self.ZMin -= s
        self.XMax += s
        self.YMax += s
        self.ZMax += s

    def move(self, v):
        v = vec(v)
        self.XMin += v.x
        self.XMax += v.x
        self.YMin += v.y
        self.YMax += v.y
        self.ZMin += v.z
        self.ZMax += v.z

    def isInside(self, *args):
        self._check()
        if len(args) == 1 and isinstance(args[0], BoundBox):
            o = args[0]
            return (o.XMin >= self.XMin and o.XMax <= self.XMax and o.YMin >= self.YMin and o.YMax <= self.YMax
                    and o.ZMin >= self.ZMin and o.ZMax <= self.ZMax)
        v = Vector(*args) if len(args) == 3 else vec(args[0])
        if v.x < self.XMin or v.x > self.XMax:
            return False
        if v.y < self.YMin or v.y > self.YMax:
            return False
        if v.z < self.ZMin or v.z > self.ZMax:
            return False
        return True

    def getPoint(self, i):
        x = (self.XMin, self.XMax)
        y = (self.YMin, self.YMax)
        z = (self.ZMin, self.ZMax)
        pts = [(x[0], y[0], z[1]), (x[1], y[0], z[1]), (x[1], y[1], z[1]), (x[0], y[1], z[1]),
               (x[0], y[0], z[0]), (x[1], y[0], z[0]), (x[1], y[1], z[0]), (x[0], y[1], z[0])]
        return Vector(*pts[i])

    @property
    def Center(self):
        return Vector((self.XMin + self.XMax) / 2.0, (self.YMin + self.YMax) / 2.0, (self.ZMin + self.ZMax) / 2.0)

    @property
    def XLength(self):
        return self.XMax - self.XMin

    @property
    def YLength(self):
        return self.YMax - self.YMin

    @property
    def ZLength(self):
        return self.ZMax - self.ZMin

    @property
    def DiagonalLength(self):
        return math.sqrt(self.XLength ** 2 + self.YLength ** 2 + self.ZLength ** 2)

    def __repr__(self):
        return f"BoundBox ({self.XMin:g}, {self.YMin:g}, {self.ZMin:g}, {self.XMax:g}, {self.YMax:g}, {self.ZMax:g})"


class Precision:
    @staticmethod
    def confusion():
        return CONFUSION

    @staticmethod
    def angular():
        return 1e-12

    @staticmethod
    def approximation():
        return 1e-6

    @staticmethod
    def parametric(*a):
        return 1e-9

    @staticmethod
    def intersection():
        return CONFUSION * 0.01

    @staticmethod
    def infinite():
        return 2e100

    @staticmethod
    def isInfinite(v):
        return abs(v) >= 1e100
