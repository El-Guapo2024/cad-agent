// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/App/Expression.cpp: 2015 Eivind Kvedalen
//   src/Base/Exception.cpp: 2002 Jürgen Riegel
//   src/Base/Quantity.cpp: 2013 Jürgen Riegel
//   src/Base/QuantityPyImp.cpp: 2013 Jürgen Riegel
//   src/Base/VectorPyImp.cpp: 2008 Werner Mayer
//   No copyright line in the file: src/Base/Unit.cpp, src/Base/Unit.h
// The values FreeCAD's expressions are made of. FreeCAD evaluates an expression through Python objects
// (App/Expression.cpp: OperatorExpression's calc() runs PyNumber_Add and its kin on whatever the operands are, and a
// FunctionExpression answers with a Quantity), so what an operator does depends on the Python types of its
// operands: an int stays exact and divides to a float, a bool is a number, a str repeats, a Quantity follows
// Base/QuantityPyImp.cpp (its own add, remainder, power and comparison, never the other operand's). This
// file holds those values and what Python and Base/Quantity.cpp do with them, with their messages, so that
// expr.ts can follow Expression.cpp line by line.
import { toNumber, typeString, unitString, userString, QuantityError, type Quantity } from './quantity'
import type { Dims } from './units-data'

export const ZERO: Dims = [0, 0, 0, 0, 0, 0, 0, 0]
export const ANGLE: Dims = [0, 0, 0, 0, 0, 0, 0, 1]

/** An exception as Python reports it: its class name and message are what evalExpression raises. */
export class PyError extends QuantityError {
  /** `raw`: a Base exception that went through Python's C API without becoming a Python exception, so that calc() does not
   *  add the "in expression:" line to it (a Quantity comparison between different units is one). */
  constructor(message: string, readonly etype: string, kind: 'syntax' | 'mismatch' | 'eval' = 'eval', readonly raw = false) {
    super(message, kind)
    this.name = etype
  }
}
/** Base::UnitsMismatchError (Python's ArithmeticError). */
export const mismatch = (message: string) => new PyError(message, 'ArithmeticError', 'mismatch')
const typeError = (message: string) => new PyError(message, 'TypeError')
/** The SystemError Python raises when a call returned a result with an exception set: its message names the call. */
export const systemError = () => new PyError('<built-in method evalExpression of FeaturePython object at 0x0> returned a result with an exception set', 'SystemError', 'eval', true)

/** Where FreeCAD does something its authors cannot have meant; off here, and on for the differential test
 *  (scripts/exprdiff.py) so that every other answer can be compared. */
export const QUIRKS = {
  /** essentiallyInteger (App/Expression.cpp) casts an integral double above INT_MAX to int, so on x86 the Python int that comes
   *  out of 3000000000, 1e10 or 2^31 as a number is -2147483648. */
  int32Cast: false,
}

export type PyVal =
  | { t: 'int'; v: bigint }
  | { t: 'float'; v: number }
  | { t: 'bool'; v: boolean }
  | { t: 'str'; v: string }
  | { t: 'none' }
  | { t: 'qty'; q: Quantity }
  | { t: 'complex'; re: number; im: number }
  | { t: 'list'; v: PyVal[] }
  | { t: 'tuple'; v: PyVal[] }
  /** Something Python prints but this evaluator cannot compute with (a Unit, a bound method ...). */
  | { t: 'obj'; type: string; str: string }
  /** Base.Vector (Base/VectorPyImp.cpp), a point or direction in mm. */
  | { t: 'vector'; v: [number, number, number] }

export const int = (v: bigint | number): PyVal => ({ t: 'int', v: BigInt(v) })
export const float = (v: number): PyVal => ({ t: 'float', v })
export const bool = (v: boolean): PyVal => ({ t: 'bool', v })
export const str = (v: string): PyVal => ({ t: 'str', v })
export const none: PyVal = { t: 'none' }
export const qty = (value: number, dims: Dims): PyVal => ({ t: 'qty', q: { value, dims } })

/** tp_name, as the messages spell it. */
export function typeName(a: PyVal): string {
  return a.t === 'qty' ? 'Base.Quantity' : a.t === 'none' ? 'NoneType' : a.t === 'obj' ? a.type : a.t === 'vector' ? 'Base.Vector' : a.t
}
export const isReal = (a: PyVal) => a.t === 'int' || a.t === 'float' || a.t === 'bool'
/** PyNumber_Check (a Vector passes it, as it sets the nb_int and nb_float slots). */
export const isNumeric = (a: PyVal) => isReal(a) || a.t === 'complex' || a.t === 'qty' || a.t === 'vector'
const isIntLike = (a: PyVal): a is { t: 'int'; v: bigint } | { t: 'bool'; v: boolean } => a.t === 'int' || a.t === 'bool'
const bigOf = (a: PyVal): bigint => (a.t === 'int' ? a.v : a.t === 'bool' ? (a.v ? 1n : 0n) : 0n)

// ─── Units (Base/Unit.cpp, Unit.h) ───────────────────────────────────────────────────────────────

export const isDimless = (d: Dims) => d.every((x) => x === 0)
export const sameDims = (a: Dims, b: Dims) => a.every((x, i) => x === b[i])
/** Unit's checkRange(): every exponent within [-8, 7]. */
export function checkRange(d: number[]): Dims {
  for (const e of d) {
    if (e >= 8) throw new PyError('Unit exponent overflow', 'OverflowError')
    if (e < -8) throw new PyError('Unit exponent underflow', 'ArithmeticError')
  }
  return d as Dims
}
export const unitMul = (a: Dims, b: Dims): Dims => checkRange(a.map((x, i) => x + b[i]))
export const unitDiv = (a: Dims, b: Dims): Dims => checkRange(a.map((x, i) => x - b[i]))
/** static_cast<int8_t>(double) as x86 does it: through a 32-bit integer, whose low byte is kept. */
export function toInt8(x: number): number {
  if (!Number.isFinite(x)) return 0
  const t = Math.trunc(x)
  if (t > 2147483647 || t < -2147483648) return 0
  return (t << 24) >> 24
}
/** Unit::pow(double). */
export function unitPow(a: Dims, exp: number): Dims {
  return checkRange(a.map((val) => {
    const num = val * exp
    if (Math.abs(Math.round(num) - num) >= Number.EPSILON) throw mismatch('pow() of unit not possible')
    return toInt8(val * exp)
  }))
}
/** Unit::root(n) (sqrt() and cbrt()). */
export function unitRoot(a: Dims, n: number): Dims {
  return checkRange(a.map((val) => {
    if (val % n !== 0) throw mismatch('unit values must be divisible by root')
    return val / n
  }))
}

// ─── Quantity (Base/Quantity.cpp) ────────────────────────────────────────────────────────────────

export const qAdd = (a: Quantity, b: Quantity): Quantity => {
  if (!sameDims(a.dims, b.dims)) throw mismatch('Quantity::operator +(): Unit mismatch in plus operation')
  return { value: a.value + b.value, dims: a.dims }
}
export const qSub = (a: Quantity, b: Quantity): Quantity => {
  if (!sameDims(a.dims, b.dims)) throw mismatch('Quantity::operator -(): Unit mismatch in minus operation')
  return { value: a.value - b.value, dims: a.dims }
}
export const qMul = (a: Quantity, b: Quantity): Quantity => ({ value: a.value * b.value, dims: unitMul(a.dims, b.dims) })
export const qDiv = (a: Quantity, b: Quantity): Quantity => ({ value: a.value / b.value, dims: unitDiv(a.dims, b.dims) })
/** Quantity::pow(const Quantity&): the unit is raised to the exponent cast to signed char. */
export function qPowQ(a: Quantity, b: Quantity): Quantity {
  if (!isDimless(b.dims)) throw mismatch('Quantity::pow(): exponent must not have a unit')
  return { value: cpow(a.value, b.value), dims: unitPow(a.dims, toInt8(b.value)) }
}
/** Quantity::pow(double). */
export const qPowD = (a: Quantity, exp: number): Quantity => ({ value: cpow(a.value, exp), dims: unitPow(a.dims, exp) })
const qLt = (a: Quantity, b: Quantity): boolean => {
  if (!sameDims(a.dims, b.dims)) throw new PyError('Quantity::operator <(): quantities need to have same unit to compare', 'ArithmeticError', 'mismatch', true)
  return a.value < b.value
}
/** Quantity::operator< and operator>, which the min and max collectors call directly. */
export const qLess = qLt
export const qGreater = (a: Quantity, b: Quantity): boolean => {
  if (!sameDims(a.dims, b.dims)) throw new PyError('Quantity::operator >(): quantities need to have same unit to compare', 'ArithmeticError', 'mismatch', true)
  return a.value > b.value
}
/** Quantity::operator+= (the sum and average collectors). */
export const qAddAssign = (a: Quantity, b: Quantity): Quantity => {
  if (!sameDims(a.dims, b.dims)) throw mismatch('Quantity::operator +=(): Unit mismatch in plus operation')
  return { value: a.value + b.value, dims: a.dims }
}
const qEq = (a: Quantity, b: Quantity) => a.value === b.value && sameDims(a.dims, b.dims)

// ─── Python's numbers ────────────────────────────────────────────────────────────────────────────

const overflow = (message: string) => new PyError(message, 'OverflowError')

/** float(int): round to nearest, an OverflowError when it does not fit. */
function floatOfInt(v: bigint): number {
  const x = Number(v)
  if (!Number.isFinite(x)) throw overflow('int too large to convert to float')
  return x
}
/** PyFloat_AsDouble on an int too big for a double fails with an OverflowError, which the C++ callers do not look at: the call
 *  goes on and Python ends it with a SystemError. */
function asDoubleOrSystemError(a: PyVal): number {
  try { return realToFloat(a) } catch { throw systemError() }
}
const realToFloat = (a: PyVal): number => (a.t === 'float' ? a.v : floatOfInt(bigOf(a)))

/** int / int, rounded once, as Python's long_true_divide rounds it. */
function intTrueDiv(a: bigint, b: bigint): number {
  if (b === 0n) throw new PyError('division by zero', 'ZeroDivisionError')
  const lim = 1n << 53n
  if (a > -lim && a < lim && b > -lim && b < lim) return Number(a) / Number(b)
  const neg = a < 0n !== b < 0n
  const x = a < 0n ? -a : a, y = b < 0n ? -b : b
  if (x === 0n) return neg ? -0 : 0
  // scale so that the quotient has 64 bits or more, keep a sticky bit for what is left over, and let Number() round once
  const bits = (n: bigint) => n.toString(2).length
  const shift = 66 - (bits(x) - bits(y))
  const num = shift >= 0 ? x << BigInt(shift) : x, den = shift >= 0 ? y : y << BigInt(-shift)
  let q = num / den
  if (num % den !== 0n) q |= 1n
  let r = Number(q)
  const s = shift
  // r * 2^-s, in two steps to stay finite
  const half = Math.trunc(s / 2)
  r = r * Math.pow(2, -half) * Math.pow(2, -(s - half))
  if (!Number.isFinite(r)) throw overflow('integer division result too large for a float')
  return neg ? -r : r
}

/** floor division remainder: the sign of the divisor. */
function intMod(a: bigint, b: bigint): bigint {
  if (b === 0n) throw new PyError('integer modulo by zero', 'ZeroDivisionError')
  let r = a % b
  if (r !== 0n && (r < 0n) !== (b < 0n)) r += b
  return r
}
function floatMod(vx: number, wx: number): number {
  if (wx === 0) throw new PyError('float modulo by zero', 'ZeroDivisionError')
  let mod = vx % wx
  if (mod !== 0) { // C's `if (mod)`: a NaN counts
    if (wx < 0 !== mod < 0) mod += wx
  } else {
    mod = wx < 0 || Object.is(wx, -0) ? -0 : 0
  }
  return mod
}

/** x ** n for a whole n, rounded once: the double x is m * 2^e with m a whole number, so m ** n is exact in BigInt. null if the
 *  answer is not a normal double. */
function exactPow(x: number, n: number): number | null {
  const view = new DataView(new ArrayBuffer(8))
  view.setFloat64(0, x)
  const hi = view.getUint32(0), lo = view.getUint32(4), biased = (hi >>> 20) & 0x7ff
  if (biased === 0) return null
  let m = (BigInt(hi & 0xfffff) << 32n) | BigInt(lo)
  m |= 1n << 52n
  if (hi >>> 31) m = -m
  const e = biased - 1075
  const k = Math.abs(n)
  const mk = m ** BigInt(k)
  const E = e * k
  try {
    const r = n >= 0 ? Number(mk) * Math.pow(2, E) : E >= 0 ? intTrueDiv(1n, mk << BigInt(E)) : intTrueDiv(1n << BigInt(-E), mk)
    return Number.isFinite(r) && Math.abs(r) >= 2.2250738585072014e-308 ? r : null
  } catch { return null }
}
/** C's pow(): the special cases of C99 (JavaScript's Math.pow differs on 1 and -1 to an infinite or NaN power), and a whole power
 *  of a double rounded once, where V8's pow can be a unit in the last place off (10 ** -5). */
export function cpow(x: number, y: number): number {
  if (x === 1 || y === 0) return 1
  if (x === -1 && (y === Infinity || y === -Infinity)) return 1
  if (Number.isInteger(y) && Math.abs(y) <= 128 && Number.isFinite(x) && x !== 0) {
    const r = exactPow(x, y)
    if (r !== null) return r
  }
  return Math.pow(x, y)
}

const isOddInteger = (x: number) => Number.isInteger(x) && Math.abs(x % 2) === 1
/** float_pow (Objects/floatobject.c): the special cases are Python's, the rest is libm's pow(). */
function floatPow(iv: number, iw: number): PyVal {
  if (iw === 0) return float(1)
  if (Number.isNaN(iv)) return float(iv)
  if (Number.isNaN(iw)) return float(iv === 1 ? 1 : iw)
  if (!Number.isFinite(iw)) {
    iv = Math.abs(iv)
    if (iv === 1) return float(1)
    return float(iw > 0 === iv > 1 ? Math.abs(iw) : 0)
  }
  if (!Number.isFinite(iv)) {
    const odd = isOddInteger(iw)
    if (iw > 0) return float(odd ? iv : Math.abs(iv))
    return float(odd ? (iv < 0 ? -0 : 0) : 0)
  }
  if (iv === 0) {
    const odd = isOddInteger(iw)
    if (iw < 0) throw new PyError('0.0 cannot be raised to a negative power', 'ZeroDivisionError')
    return float(odd ? iv : 0)
  }
  let negate = false
  if (iv < 0) {
    if (iw !== Math.floor(iw)) return complexPow({ re: iv, im: 0 }, { re: iw, im: 0 })
    iv = -iv
    negate = isOddInteger(iw)
  }
  if (iv === 1) return float(negate ? -1 : 1)
  let ix = cpow(iv, iw)
  if (!Number.isFinite(ix)) throw overflow("(34, 'Result too large')")
  if (negate) ix = -ix
  return float(ix)
}

type C = { re: number; im: number }
/** _Py_c_pow for a complex or real base and exponent. */
function complexPow(a: C, b: C): PyVal {
  if (b.re === 0 && b.im === 0) return { t: 'complex', re: 1, im: 0 }
  if (a.re === 0 && a.im === 0) {
    if (b.im !== 0 || b.re < 0) throw new PyError('0.0 to a negative or complex power', 'ZeroDivisionError')
    return { t: 'complex', re: 0, im: 0 }
  }
  const vabs = Math.hypot(a.re, a.im)
  let len = cpow(vabs, b.re)
  const at = Math.atan2(a.im, a.re)
  let phase = at * b.re
  if (b.im !== 0) {
    len /= Math.exp(at * b.im)
    phase += b.im * Math.log(vabs)
  }
  const re = len * Math.cos(phase), im = len * Math.sin(phase)
  if (!Number.isFinite(re) || !Number.isFinite(im)) {
    if (Number.isFinite(a.re) && Number.isFinite(a.im) && Number.isFinite(b.re) && Number.isFinite(b.im)) throw overflow('complex exponentiation')
  }
  return { t: 'complex', re, im }
}
const toC = (a: PyVal): C => (a.t === 'complex' ? a : { re: realToFloat(a), im: 0 })

/** The longest string, list or tuple, and the widest % field, an expression may make here: Python would build a longer one
 *  (or run out of memory), a browser tab would freeze or crash first. Past it: a MemoryError, as for the int powers below. */
const MAX_LENGTH = 10_000_000
const fits = (length: number): number => {
  if (length > MAX_LENGTH) throw new PyError('result too large to compute here', 'MemoryError')
  return length
}
const sized = <T>(length: number, make: () => T): T => (fits(length), make())

/** int ** int: exact for a non-negative exponent, else the float answer. */
function intPow(a: bigint, b: bigint): PyVal {
  if (b < 0n) return floatPow(floatOfInt(a), floatOfInt(b))
  if (a === 0n || a === 1n || b === 0n) return { t: 'int', v: b === 0n ? 1n : a }
  if (a === -1n) return { t: 'int', v: b % 2n === 0n ? 1n : -1n }
  const bits = BigInt((a < 0n ? -a : a).toString(2).length) * b
  if (bits > 4_000_000n) throw new PyError('integer power too large to compute here', 'MemoryError')
  return { t: 'int', v: a ** b }
}

// ─── What FreeCAD makes of a number ─────────────────────────────────────────────────────────────

/** pyFromQuantity (App/Expression.cpp): a quantity with a unit stays one; a plain number becomes a Python int when it is a whole
 *  number (essentiallyInteger), else a float. */
export function fromQuantity(q: Quantity): PyVal {
  if (!isDimless(q.dims)) return { t: 'qty', q }
  const v = q.value
  if (Number.isFinite(v) && Number.isInteger(v)) {
    if (v < 0) {
      if (v >= -2147483648) return int(v)
      if (v >= -9223372036854775808) return int(BigInt(v))
    } else if (v <= 2147483647) return int(v)
    else if (v <= 9223372036854775808) return QUIRKS.int32Cast ? int(-2147483648) : int(BigInt(v))
  }
  return float(v)
}
/** pyToQuantity (App/Expression.cpp): a Quantity, a float or an int; null for anything else. A bool is an int to Python. */
export function toQuantity(a: PyVal): Quantity | null {
  if (a.t === 'qty') return a.q
  if (a.t === 'float') return { value: a.v, dims: ZERO }
  if (isIntLike(a)) {
    const v = bigOf(a)
    // PyLong_AsLong fails past a C long; FreeCAD does not look, and Python then reports a SystemError. Here: the OverflowError behind it.
    if (v > 9223372036854775807n || v < -9223372036854775808n) throw new PyError('Python int too large to convert to C long', 'OverflowError')
    return { value: Number(v), dims: ZERO }
  }
  return null
}

// ─── Truth, comparison ──────────────────────────────────────────────────────────────────────────

/** PyObject_IsTrue. A Quantity is true unless its value is zero (QuantityPy::number_nonzero_handler). */
export function truth(a: PyVal): boolean {
  switch (a.t) {
    case 'int': return a.v !== 0n
    case 'float': return a.v !== 0
    case 'bool': return a.v
    case 'str': return a.v.length > 0
    case 'none': return false
    case 'qty': return a.q.value !== 0
    case 'complex': return a.re !== 0 || a.im !== 0
    case 'list': case 'tuple': return a.v.length > 0
    default: return true
  }
}

export type CmpOp = 'eq' | 'ne' | 'lt' | 'le' | 'gt' | 'ge'
const SYM: Record<CmpOp, string> = { eq: '==', ne: '!=', lt: '<', le: '<=', gt: '>', ge: '>=' }
const SWAP: Record<CmpOp, CmpOp> = { eq: 'eq', ne: 'ne', lt: 'gt', le: 'ge', gt: 'lt', ge: 'le' }

function relNum(a: number | bigint, b: number | bigint, op: CmpOp): boolean {
  switch (op) {
    case 'eq': return typeof a === typeof b ? a === b : a == b // eslint-disable-line eqeqeq
    case 'ne': return !relNum(a, b, 'eq')
    case 'lt': return a < b
    case 'le': return a <= b
    case 'gt': return a > b
    case 'ge': return a >= b
  }
}
const numOf = (a: PyVal): number | bigint => (a.t === 'float' ? a.v : bigOf(a))
function cmpStr(a: string, b: string, op: CmpOp): boolean {
  if (op === 'eq') return a === b
  if (op === 'ne') return a !== b
  const x = Array.from(a, (c) => c.codePointAt(0)!), y = Array.from(b, (c) => c.codePointAt(0)!)
  let i = 0
  while (i < x.length && i < y.length && x[i] === y[i]) i++
  const c = i < x.length && i < y.length ? x[i] - y[i] : x.length - y.length
  return op === 'lt' ? c < 0 : op === 'le' ? c <= 0 : op === 'gt' ? c > 0 : c >= 0
}
/** list and tuple: the first pair of items that differ decides (list_richcompare). */
function cmpSeq(a: PyVal[], b: PyVal[], op: CmpOp): boolean {
  if (a.length !== b.length && (op === 'eq' || op === 'ne')) return op === 'ne'
  let i = 0
  while (i < a.length && i < b.length && compare(a[i], b[i], 'eq')) i++
  if (i >= a.length || i >= b.length) return relNum(a.length, b.length, op)
  if (op === 'eq') return false
  if (op === 'ne') return true
  return compare(a[i], b[i], op)
}

/** PyObject_RichCompareBool(a, b, op) with FreeCAD's types: Base/QuantityPyImp.cpp richCompare for a Quantity, which compares
 *  two quantities by value and unit, a Quantity and any other number by value alone. */
export function compare(a: PyVal, b: PyVal, op: CmpOp): boolean {
  if (a.t === 'qty' && b.t === 'qty') {
    const u1 = a.q, u2 = b.q
    switch (op) {
      case 'ne': return !qEq(u1, u2)
      case 'lt': return qLt(u1, u2)
      case 'le': return qLt(u1, u2) || qEq(u1, u2)
      case 'gt': return !qLt(u1, u2) && !qEq(u1, u2)
      case 'ge': return !qLt(u1, u2)
      case 'eq': return qEq(u1, u2)
    }
  }
  if (a.t === 'vector' && b.t === 'vector') {
    if (op !== 'eq' && op !== 'ne') throw typeError('no ordering relation is defined for Vector')
    const eq = a.v.every((x, i) => Math.abs(x - b.v[i]) <= Number.EPSILON)
    return op === 'eq' ? eq : !eq
  }
  if ((a.t === 'qty' && isNumeric(b)) || (b.t === 'qty' && isNumeric(a))) {
    // PyFloat_AsDouble of each: a complex has none, and refuses
    const dbl = (x: PyVal): number => {
      if (x.t === 'qty') return x.q.value
      if (x.t === 'complex') throw typeError("must be real number, not complex")
      if (x.t === 'vector') throw systemError() // PyFloat_AsDouble fails and the comparison goes on with the error set
      return asDoubleOrSystemError(x)
    }
    const u1 = dbl(a), u2 = dbl(b)
    return relNum(u1, u2, op)
  }
  if (isReal(a) && isReal(b)) return relNum(numOf(a), numOf(b), op)
  if (a.t === 'complex' || b.t === 'complex') {
    if ((a.t === 'complex' || isReal(a)) && (b.t === 'complex' || isReal(b))) {
      if (op !== 'eq' && op !== 'ne') throw typeError(`'${SYM[op]}' not supported between instances of '${typeName(a)}' and '${typeName(b)}'`)
      const x = toC(a), y = toC(b)
      const eq = x.re === y.re && x.im === y.im
      return op === 'eq' ? eq : !eq
    }
  }
  if (a.t === 'str' && b.t === 'str') return cmpStr(a.v, b.v, op)
  if (a.t === 'list' && b.t === 'list') return cmpSeq(a.v, b.v, op)
  if (a.t === 'tuple' && b.t === 'tuple') return cmpSeq(a.v, b.v, op)
  if (a.t === 'none' && b.t === 'none') { if (op === 'eq') return true; if (op === 'ne') return false }
  if (a.t === 'obj' && b.t === 'obj' && (op === 'eq' || op === 'ne')) return (a.str === b.str) === (op === 'eq')
  if (op === 'eq') return false
  if (op === 'ne') return true
  throw typeError(`'${SYM[op]}' not supported between instances of '${typeName(a)}' and '${typeName(b)}'`)
}

// ─── Arithmetic ─────────────────────────────────────────────────────────────────────────────────

export type BinOp = 'add' | 'sub' | 'mul' | 'div' | 'mod' | 'pow'
/** calc() runs PyNumber_InPlaceRemainder for "%", so its message says "%=". */
const SYMBOL: Record<BinOp, string> = { add: '+', sub: '-', mul: '*', div: '/', mod: '%=', pow: '** or pow()' }

/** Base::QuantityPy's pyToQuantity (QuantityPyImp.cpp): a Quantity, a float or an int, else a TypeError. */
function qOperand(a: PyVal): Quantity {
  if (a.t === 'qty') return a.q
  const q = isReal(a) ? toQuantity(a) : null
  if (!q) throw typeError(`Cannot convert ${typeName(a)} to Quantity`)
  return q
}

/** QuantityPy's number_*_handler, which Python calls when either operand is a Quantity (the left one first). */
function quantityOp(op: BinOp, a: PyVal, b: PyVal): PyVal {
  switch (op) {
    case 'add': case 'sub': case 'mul': case 'div': {
      const x = qOperand(a), y = qOperand(b)
      return { t: 'qty', q: op === 'add' ? qAdd(x, y) : op === 'sub' ? qSub(x, y) : op === 'mul' ? qMul(x, y) : qDiv(x, y) }
    }
    case 'mod': {
      if (a.t !== 'qty') throw typeError('First arg must be Quantity')
      let d2: number
      if (b.t === 'qty') d2 = b.q.value
      else if (b.t === 'float') d2 = b.v
      else if (isIntLike(b)) d2 = Number(toQuantity(b)!.value)
      else throw typeError('Expected quantity or number')
      return { t: 'qty', q: { value: floatMod(a.q.value, d2), dims: a.q.dims } }
    }
    case 'pow': {
      if (a.t !== 'qty') throw typeError('First arg must be Quantity')
      if (b.t === 'qty') return { t: 'qty', q: qPowQ(a.q, b.q) }
      if (b.t === 'float') return { t: 'qty', q: qPowD(a.q, b.v) }
      if (isIntLike(b)) return { t: 'qty', q: qPowD(a.q, toQuantity(b)!.value) }
      throw typeError('Expected quantity or number')
    }
  }
}

/** The Vector helpers of Base/Vector3D.cpp. */
type V3 = [number, number, number]
export const vecSub = (a: V3, b: V3): V3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]]
export const vecAdd = (a: V3, b: V3): V3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]]
export const vecScale = (a: V3, f: number): V3 => [a[0] * f, a[1] * f, a[2] * f]
export const vecDot = (a: V3, b: V3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
export const vecCross = (a: V3, b: V3): V3 => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]
export const vecLength = (a: V3) => Math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])
export const vecSqr = (a: V3) => a[0] * a[0] + a[1] * a[1] + a[2] * a[2]
export const vector = (v: V3): PyVal => ({ t: 'vector', v })

/** VectorPy's number handlers (Base/VectorPyImp.cpp), which Python calls when either operand is a Vector. */
function vectorOp(op: BinOp, a: PyVal, b: PyVal): PyVal {
  const tn = (x: PyVal) => typeName(x)
  const scalar = (x: PyVal): number => {
    if (x.t === 'qty') return x.q.value
    if (x.t === 'complex') throw typeError('must be real number, not complex')
    return asDoubleOrSystemError(x)
  }
  switch (op) {
    case 'add': case 'sub': {
      if (a.t !== 'vector') throw typeError('First arg must be Vector')
      if (b.t !== 'vector') throw typeError('Second arg must be Vector')
      return vector(op === 'add' ? vecAdd(a.v, b.v) : vecSub(a.v, b.v))
    }
    case 'mul': {
      if (a.t === 'vector') {
        if (b.t === 'vector') return float(vecDot(a.v, b.v))
        if (isNumeric(b)) return vector(vecScale(a.v, scalar(b)))
        throw typeError('A Vector can only be multiplied by Vector or number')
      }
      if (b.t === 'vector' && isNumeric(a)) return vector(vecScale(b.v, scalar(a)))
      if (b.t === 'vector') throw typeError('A Vector can only be multiplied by Vector or number')
      throw typeError('First or second arg must be Vector')
    }
    case 'div': {
      if (a.t === 'vector' && isNumeric(b)) {
        if (b.t === 'vector') throw typeError(`unsupported operand type(s) for /: '${tn(a)}' and '${tn(b)}'`)
        const d = scalar(b)
        if (d === 0) throw new PyError(`'${tn(a)}' division by zero`, 'ZeroDivisionError')
        return vector([a.v[0] / d, a.v[1] / d, a.v[2] / d])
      }
      throw typeError(`unsupported operand type(s) for /: '${tn(a)}' and '${tn(b)}'`)
    }
    case 'mod':
      if (a.t === 'vector' && b.t === 'vector') return vector(vecCross(a.v, b.v))
      throw typeError(`unsupported operand type(s) for %: '${tn(a)}' and '${tn(b)}'`)
    case 'pow': throw typeError(`unsupported operand type(s) for ** or pow(): '${tn(a)}' and '${tn(b)}'`)
  }
}

function seqRepeat(seq: PyVal, n: PyVal): PyVal {
  if (!isIntLike(n)) throw typeError(`can't multiply sequence by non-int of type '${typeName(n)}'`)
  const count = bigOf(n)
  if (count > 1n << 31n) throw new PyError('', 'MemoryError')
  const k = Number(count < 0n ? 0n : count)
  if (seq.t === 'str') return str(sized(seq.v.length * k, () => seq.v.repeat(k)))
  const items = (seq as { v: PyVal[] }).v
  return { t: seq.t as 'list' | 'tuple', v: sized(items.length * k, () => Array.from({ length: k }, () => items).flat()) }
}
const isSeq = (a: PyVal) => a.t === 'str' || a.t === 'list' || a.t === 'tuple'

/** PyNumber_Add and its kin, for FreeCAD's operand types. */
export function binary(op: BinOp, a: PyVal, b: PyVal): PyVal {
  if (op === 'mod' && a.t === 'str') return str(percentFormat(a.v, b)) // calc() formats a str on the left, whatever is on the right
  // Python asks the left operand's type first: a Quantity answers (or refuses), a Vector answers, and a number, str or list
  // has nothing for a Vector and leaves it to the Vector's own handler
  if (a.t === 'qty') return quantityOp(op, a, b)
  if (a.t === 'vector' || b.t === 'vector') return vectorOp(op, a, b)
  if (b.t === 'qty') return quantityOp(op, a, b)
  const bothInt = isIntLike(a) && isIntLike(b)
  const bothReal = isReal(a) && isReal(b)
  if (bothReal || ((a.t === 'complex' || isReal(a)) && (b.t === 'complex' || isReal(b)))) {
    if (a.t === 'complex' || b.t === 'complex') return complexOp(op, a, b)
    switch (op) {
      case 'add': return bothInt ? { t: 'int', v: bigOf(a) + bigOf(b) } : float(realToFloat(a) + realToFloat(b))
      case 'sub': return bothInt ? { t: 'int', v: bigOf(a) - bigOf(b) } : float(realToFloat(a) - realToFloat(b))
      case 'mul': return bothInt ? { t: 'int', v: bigOf(a) * bigOf(b) } : float(realToFloat(a) * realToFloat(b))
      case 'div': {
        if (bothInt) return float(intTrueDiv(bigOf(a), bigOf(b)))
        const x = realToFloat(a), y = realToFloat(b)
        if (y === 0) throw new PyError('float division by zero', 'ZeroDivisionError')
        return float(x / y)
      }
      case 'mod': return bothInt ? { t: 'int', v: intMod(bigOf(a), bigOf(b)) } : float(floatMod(realToFloat(a), realToFloat(b)))
      case 'pow': return bothInt ? intPow(bigOf(a), bigOf(b)) : floatPow(realToFloat(a), realToFloat(b))
    }
  }
  switch (op) {
    case 'add':
      if (a.t === 'str' && b.t === 'str') return str(sized(a.v.length + b.v.length, () => a.v + b.v))
      if (a.t === 'list' && b.t === 'list') return { t: 'list', v: sized(a.v.length + b.v.length, () => [...a.v, ...b.v]) }
      if (a.t === 'tuple' && b.t === 'tuple') return { t: 'tuple', v: sized(a.v.length + b.v.length, () => [...a.v, ...b.v]) }
      if (a.t === 'str') throw typeError(`can only concatenate str (not "${typeName(b)}") to str`)
      if (a.t === 'list') throw typeError(`can only concatenate list (not "${typeName(b)}") to list`)
      if (a.t === 'tuple') throw typeError(`can only concatenate tuple (not "${typeName(b)}") to tuple`)
      break
    case 'mul':
      if (isSeq(a) && !isSeq(b)) return seqRepeat(a, b)
      if (isSeq(b) && !isSeq(a)) return seqRepeat(b, a)
      if (isSeq(a) && isSeq(b)) throw typeError(`can't multiply sequence by non-int of type '${typeName(b)}'`)
      break
  }
  throw typeError(`unsupported operand type(s) for ${SYMBOL[op]}: '${typeName(a)}' and '${typeName(b)}'`)
}

function complexOp(op: BinOp, a: PyVal, b: PyVal): PyVal {
  if (op === 'mod') throw typeError(`unsupported operand type(s) for %=: '${typeName(a)}' and '${typeName(b)}'`)
  const x = toC(a), y = toC(b)
  switch (op) {
    case 'add': return { t: 'complex', re: x.re + y.re, im: x.im + y.im }
    case 'sub': return { t: 'complex', re: x.re - y.re, im: x.im - y.im }
    case 'mul': return { t: 'complex', re: x.re * y.re - x.im * y.im, im: x.re * y.im + x.im * y.re }
    case 'div': {
      const d = y.re * y.re + y.im * y.im
      if (d === 0) throw new PyError('division by zero', 'ZeroDivisionError')
      // Smith's method, as _Py_c_quot does it
      const abs_breal = Math.abs(y.re), abs_bimag = Math.abs(y.im)
      if (abs_breal >= abs_bimag) {
        if (abs_breal === 0) throw new PyError('division by zero', 'ZeroDivisionError')
        const ratio = y.im / y.re, dd = y.re + y.im * ratio
        return { t: 'complex', re: (x.re + x.im * ratio) / dd, im: (x.im - x.re * ratio) / dd }
      }
      const ratio = y.re / y.im, dd = y.re * ratio + y.im
      return { t: 'complex', re: (x.re * ratio + x.im) / dd, im: (x.im * ratio - x.re) / dd }
    }
    case 'pow': return complexPow(x, y)
    default: throw typeError('unsupported operand type')
  }
}

/** PyNumber_Negative. */
export function neg(a: PyVal): PyVal {
  switch (a.t) {
    case 'int': return { t: 'int', v: -a.v }
    case 'bool': return { t: 'int', v: a.v ? -1n : 0n }
    case 'float': return float(-a.v)
    case 'complex': return { t: 'complex', re: -a.re, im: -a.im }
    case 'qty': return { t: 'qty', q: { value: a.q.value * -1, dims: a.q.dims } }
    case 'vector': return vector([-a.v[0], -a.v[1], -a.v[2]])
    default: throw typeError(`bad operand type for unary -: '${typeName(a)}'`)
  }
}
/** PyNumber_Positive. */
export function pos(a: PyVal): PyVal {
  switch (a.t) {
    case 'int': case 'float': case 'complex': return a
    case 'bool': return { t: 'int', v: a.v ? 1n : 0n }
    case 'qty': return { t: 'qty', q: { value: a.q.value, dims: a.q.dims } }
    case 'vector': return vector([a.v[0], a.v[1], a.v[2]])
    default: throw typeError(`bad operand type for unary +: '${typeName(a)}'`)
  }
}

// ─── Printing ───────────────────────────────────────────────────────────────────────────────────

/** repr(float): the shortest digits that read back, in Python's layout. `dot` keeps the ".0" of a whole number. */
export function floatRepr(x: number, dot = true): string {
  if (Number.isNaN(x)) return 'nan'
  if (!Number.isFinite(x)) return x > 0 ? 'inf' : '-inf'
  if (x === 0) return (Object.is(x, -0) ? '-0' : '0') + (dot ? '.0' : '')
  const [m, e] = Math.abs(x).toExponential().split('e')
  const digits = m.replace('.', ''), exp = Number(e)
  let s: string
  if (exp < -4 || exp >= 16) s = digits[0] + (digits.length > 1 ? '.' + digits.slice(1) : '') + 'e' + (exp < 0 ? '-' : '+') + String(Math.abs(exp)).padStart(2, '0')
  else if (exp >= 0) s = digits.length <= exp + 1 ? digits.padEnd(exp + 1, '0') + (dot ? '.0' : '') : digits.slice(0, exp + 1) + '.' + digits.slice(exp + 1)
  else s = '0.' + '0'.repeat(-exp - 1) + digits
  return (x < 0 ? '-' : '') + s
}
function complexRepr(re: number, im: number): string {
  const r = floatRepr(re, false)
  const i = floatRepr(im, false)
  if (re === 0 && !Object.is(re, -0)) return `${i}j`
  return `(${r}${im < 0 || Object.is(im, -0) || i.startsWith('-') ? '' : '+'}${i}j)`
}
/** repr(str). */
export function strRepr(s: string): string {
  const quote = s.includes("'") && !s.includes('"') ? '"' : "'"
  let out = quote
  for (const ch of s) {
    const c = ch.codePointAt(0)!
    if (ch === quote || ch === '\\') out += '\\' + ch
    else if (ch === '\n') out += '\\n'
    else if (ch === '\r') out += '\\r'
    else if (ch === '\t') out += '\\t'
    else if (c < 0x20 || c === 0x7f) out += '\\x' + c.toString(16).padStart(2, '0')
    else if (c >= 0x80 && c < 0xa0) out += '\\x' + c.toString(16).padStart(2, '0')
    else if (c === 0xad || (c >= 0x2028 && c <= 0x2029) || (c >= 0xd800 && c <= 0xdfff)) out += '\\u' + c.toString(16).padStart(4, '0')
    else out += ch
  }
  return out + quote
}
/** repr(obj). */
export function repr(a: PyVal): string {
  switch (a.t) {
    case 'int': return a.v.toString()
    case 'float': return floatRepr(a.v)
    case 'bool': return a.v ? 'True' : 'False'
    case 'str': return strRepr(a.v)
    case 'none': return 'None'
    case 'qty': return floatRepr(a.q.value) + (isDimless(a.q.dims) ? '' : ' ' + unitString(a.q.dims))
    case 'complex': return complexRepr(a.re, a.im)
    case 'list': return '[' + a.v.map(repr).join(', ') + ']'
    case 'tuple': return a.v.length === 1 ? `(${repr(a.v[0])},)` : '(' + a.v.map(repr).join(', ') + ')'
    case 'obj': return a.str
    case 'vector': return `Vector (${floatRepr(a.v[0])}, ${floatRepr(a.v[1])}, ${floatRepr(a.v[2])})`
  }
}
/** str(obj). */
export const pyStr = (a: PyVal): string => (a.t === 'str' ? a.v : repr(a))

// ─── "%" formatting of a str ────────────────────────────────────────────────────────────────────

function intToIndex(a: PyVal, spec: string): bigint {
  if (isIntLike(a)) return bigOf(a)
  throw typeError(`%${spec} format: an integer is required, not ${typeName(a)}`)
}
/** PyNumber_Long for a %d: ints, floats (truncated) and Quantity (its value, as a C long). */
function longOf(a: PyVal, spec: string): bigint {
  if (isIntLike(a)) return bigOf(a)
  if (a.t === 'float') {
    if (!Number.isFinite(a.v)) throw new PyError(Number.isNaN(a.v) ? 'cannot convert float NaN to integer' : 'cannot convert float infinity to integer', Number.isNaN(a.v) ? 'ValueError' : 'OverflowError')
    return BigInt(Math.trunc(a.v))
  }
  if (a.t === 'qty') return BigInt(Math.trunc(a.q.value))
  throw typeError(`%${spec} format: a real number is required, not ${typeName(a)}`)
}
function floatArg(a: PyVal, spec: string): number {
  if (a.t === 'float') return a.v
  if (isIntLike(a)) return floatOfInt(bigOf(a))
  if (a.t === 'qty') return a.q.value
  throw typeError(`must be real number, not ${typeName(a)}`)
}
function expFormat(v: number, prec: number, upper: boolean): string {
  const s = toNumber(v, 'Scientific', prec)
  return upper ? s.toUpperCase() : s
}
function genFormat(v: number, prec: number, alt: boolean, upper: boolean): string {
  let s: string
  if (!alt) s = toNumber(v, 'Default', prec)
  else { // "#": the point stays and so do the trailing zeros
    const sci = toNumber(v, 'Scientific', prec - 1)
    const X = Number(sci.slice(sci.indexOf('e') + 1))
    s = X >= -4 && X < prec ? toNumber(v, 'Fixed', prec - 1 - X) : sci
    if (!s.includes('.')) s = s.includes('e') ? s.replace('e', '.e') : s + '.'
  }
  return upper ? s.toUpperCase() : s
}

/** PyUnicode_Format: the right operand is the one value, or the items of a tuple. */
export function percentFormat(fmt: string, arg: PyVal): string {
  const args: PyVal[] = arg.t === 'tuple' ? arg.v : [arg]
  let ai = 0
  const next = (): PyVal => {
    if (ai >= args.length) throw typeError('not enough arguments for format string')
    return args[ai++]
  }
  let out = ''
  const chars = Array.from(fmt)
  let i = 0
  while (i < chars.length) {
    const ch = chars[i]
    if (ch !== '%') { out += ch; i++; continue }
    i++
    if (chars[i] === '(') {
      if (arg.t === 'list') throw typeError('list indices must be integers or slices, not str')
      throw typeError('format requires a mapping')
    }
    const flags = { minus: false, plus: false, space: false, alt: false, zero: false }
    for (; i < chars.length; i++) {
      const f = chars[i]
      if (f === '-') flags.minus = true
      else if (f === '+') flags.plus = true
      else if (f === ' ') flags.space = true
      else if (f === '#') flags.alt = true
      else if (f === '0') flags.zero = true
      else break
    }
    let width = -1, prec = -1
    if (chars[i] === '*') {
      const w = next()
      if (!isIntLike(w)) throw typeError('* wants int')
      if (bigOf(w) > 9223372036854775807n || bigOf(w) < -9223372036854775808n) throw overflow('Python int too large to convert to C ssize_t')
      width = Number(bigOf(w))
      if (width < 0) { flags.minus = true; width = -width }
      i++
    } else {
      let w = ''
      while (i < chars.length && /[0-9]/.test(chars[i])) w += chars[i++]
      if (w) width = Number(w)
    }
    if (chars[i] === '.') {
      i++
      if (chars[i] === '*') {
        const p = next()
        if (!isIntLike(p)) throw typeError('* wants int')
        if (bigOf(p) > 2147483647n || bigOf(p) < -2147483648n) throw overflow('Python int too large to convert to C int')
        prec = Math.max(0, Number(bigOf(p)))
        i++
      } else {
        let p = ''
        while (i < chars.length && /[0-9]/.test(chars[i])) p += chars[i++]
        prec = p ? Number(p) : 0
      }
    }
    if (i < chars.length && 'hlL'.includes(chars[i])) i++ // one length modifier is skipped
    if (i >= chars.length) throw new PyError('incomplete format', 'ValueError')
    const conv = chars[i++]
    if (conv === '%' && !(flags.minus || flags.plus || flags.space || flags.alt || flags.zero || width >= 0 || prec >= 0)) { out += '%'; continue }
    const a = next()
    fits(width); fits(prec) // once the argument is there, as Python checks it first
    let body: string, sign = '', numeric = true
    switch (conv) {
      case 's': body = pyStr(a); numeric = false; if (prec >= 0) body = Array.from(body).slice(0, prec).join(''); break
      case 'r': body = repr(a); numeric = false; if (prec >= 0) body = Array.from(body).slice(0, prec).join(''); break
      case 'a': body = repr(a).replace(/[^\x00-\x7f]/gu, (c) => { const n = c.codePointAt(0)!; return n < 0x100 ? '\\x' + n.toString(16).padStart(2, '0') : n < 0x10000 ? '\\u' + n.toString(16).padStart(4, '0') : '\\U' + n.toString(16).padStart(8, '0') }); numeric = false; if (prec >= 0) body = body.slice(0, prec); break
      case 'c': {
        numeric = false
        if (isIntLike(a)) { const n = bigOf(a); if (n < 0n || n > 0x10ffffn) throw new PyError('%c arg not in range(0x110000)', 'OverflowError'); body = String.fromCodePoint(Number(n)) }
        else if (a.t === 'str' && Array.from(a.v).length === 1) body = a.v
        else throw typeError('%c requires int or char')
        break
      }
      case 'd': case 'i': case 'u': {
        const n = longOf(a, conv)
        sign = n < 0n ? '-' : flags.plus ? '+' : flags.space ? ' ' : ''
        body = (n < 0n ? -n : n).toString()
        if (prec >= 0) body = body.padStart(prec, '0')
        break
      }
      case 'x': case 'X': case 'o': {
        const n = intToIndex(a, conv)
        sign = n < 0n ? '-' : flags.plus ? '+' : flags.space ? ' ' : ''
        body = (n < 0n ? -n : n).toString(conv === 'o' ? 8 : 16)
        if (conv === 'X') body = body.toUpperCase()
        if (prec >= 0) body = body.padStart(prec, '0')
        if (flags.alt) body = (conv === 'o' ? '0o' : conv === 'x' ? '0x' : '0X') + body
        break
      }
      case 'e': case 'E': case 'f': case 'F': case 'g': case 'G': {
        const v = floatArg(a, conv)
        const p = prec < 0 ? 6 : prec
        if (!Number.isFinite(v)) { body = Number.isNaN(v) ? 'nan' : 'inf'; sign = v < 0 ? '-' : flags.plus ? '+' : flags.space ? ' ' : ''; if ('EFG'.includes(conv)) body = body.toUpperCase(); flags.zero = false; break }
        const neg = v < 0 || Object.is(v, -0)
        sign = neg ? '-' : flags.plus ? '+' : flags.space ? ' ' : ''
        const av = Math.abs(v)
        if (conv === 'e' || conv === 'E') { body = expFormat(av, p, conv === 'E'); if (flags.alt && p === 0) body = body.replace(/e/i, (m) => '.' + m) }
        else if (conv === 'f' || conv === 'F') { body = toNumber(av, 'Fixed', p); if (flags.alt && p === 0) body += '.' }
        else body = genFormat(av, p === 0 ? 1 : p, flags.alt, conv === 'G')
        break
      }
      default:
        {
        const c = conv.codePointAt(0)!
        throw new PyError(`unsupported format character '${c >= 31 && c <= 126 ? conv : '?'}' (0x${c.toString(16)}) at index ${i - 1}`, 'ValueError')
      }
    }
    let text = sign + body
    if (width > text.length) {
      if (flags.minus) text = text.padEnd(width, ' ')
      else if (flags.zero && numeric) text = sign + body.padStart(width - sign.length, '0')
      else text = text.padStart(width, ' ')
    }
    out = sized(out.length + text.length, () => out + text)
  }
  // a list or a Vector is a mapping to PyUnicode_Format, which then does not mind arguments left over
  if (ai < args.length && arg.t !== 'list' && arg.t !== 'vector') throw typeError('not all arguments converted during string formatting')
  return out
}

// ─── Components: a[i], a[i:j:k], a.name ─────────────────────────────────────────────────────────

function indexOf(i: PyVal, what: string, len: number): number {
  if (!isIntLike(i)) throw typeError(`${what} indices must be integers${what === 'string' ? '' : ' or slices'}, not '${typeName(i)}'`)
  let n = Number(bigOf(i))
  if (n < 0) n += len
  if (n < 0 || n >= len) throw new PyError(`${what} index out of range`, 'IndexError')
  return n
}
/** PyObject_GetItem on a str, list or tuple; what Py::Sequence does to anything else. */
export function getItem(obj: PyVal, index: PyVal): PyVal {
  if (obj.t === 'str') {
    const cps = Array.from(obj.v)
    return str(cps[indexOf(index, 'string', cps.length)])
  }
  if (obj.t === 'list') return obj.v[indexOf(index, 'list', obj.v.length)]
  if (obj.t === 'tuple') return obj.v[indexOf(index, 'tuple', obj.v.length)]
  throw typeError(`PyCXX: Error creating object of type N2Py7SeqBaseINS_6ObjectEEE from ${repr(obj)}`)
}
/** A slice object applied (PySlice_New + PyObject_GetItem). Each bound is None or an int. */
export function getSlice(obj: PyVal, lo: PyVal | null, hi: PyVal | null, step: PyVal | null): PyVal {
  const bound = (b: PyVal | null): bigint | null => {
    if (b === null || b.t === 'none') return null
    if (!isIntLike(b)) throw typeError('slice indices must be integers or None or have an __index__ method')
    return bigOf(b)
  }
  const items: PyVal[] | string[] | null = obj.t === 'str' ? Array.from(obj.v) : obj.t === 'list' || obj.t === 'tuple' ? obj.v : null
  if (!items) throw typeError(`PyCXX: Error creating object of type N2Py7SeqBaseINS_6ObjectEEE from ${repr(obj)}`)
  const s = bound(step) ?? 1n
  if (s === 0n) throw new PyError('slice step cannot be zero', 'ValueError')
  const n = BigInt(items.length)
  const clamp = (b: bigint | null, dflt: bigint, lowest: bigint, highest: bigint): bigint => {
    if (b === null) return dflt
    if (b < 0n) { b += n; if (b < 0n) b = s < 0n ? lowest : 0n }
    else if (b >= n) b = s < 0n ? highest : n
    return b
  }
  const start = clamp(bound(lo), s < 0n ? n - 1n : 0n, -1n, n - 1n)
  const stop = clamp(bound(hi), s < 0n ? -1n : n, -1n, n - 1n)
  const picked: (PyVal | string)[] = []
  if (s > 0n) for (let k = start; k < stop; k += s) picked.push(items[Number(k)])
  else for (let k = start; k > stop; k += s) picked.push(items[Number(k)])
  if (obj.t === 'str') return str((picked as string[]).join(''))
  return obj.t === 'list' ? { t: 'list', v: picked as PyVal[] } : { t: 'tuple', v: picked as PyVal[] }
}
/** Attribute access (ObjectIdentifier::Component::get on a Python value): what a number, a Quantity or a str offers here. */
export function getAttr(obj: PyVal, name: string): PyVal {
  const noAttr = () => new PyError(`No attribute named '${name}'`, 'AttributeError')
  switch (obj.t) {
    case 'qty':
      if (name === 'Value') return float(obj.q.value)
      if (name === 'Unit') return { t: 'obj', type: 'Unit', str: unitObjectString(obj.q.dims) }
      if (name === 'UserString') return str(userString(obj.q).text)
      throw noAttr()
    case 'int': case 'bool':
      if (name === 'real' || name === 'numerator') return { t: 'int', v: bigOf(obj) }
      if (name === 'imag') return int(0)
      if (name === 'denominator') return int(1)
      throw noAttr()
    case 'float':
      if (name === 'real') return obj
      if (name === 'imag') return float(0)
      throw noAttr()
    case 'complex':
      if (name === 'real') return float(obj.re)
      if (name === 'imag') return float(obj.im)
      throw noAttr()
    default: throw noAttr()
  }
}
/** Unit::representation(): "Unit: mm (1,0,0,0,0,0,0,0) [Length]". */
function unitObjectString(dims: Dims): string {
  const type = typeString(dims)
  return `Unit: ${unitString(dims)} (${dims.join(',')})${type ? ` [${type}]` : ''}`
}
