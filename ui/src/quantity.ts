// FreeCAD's quantities, ported from src/Base/ at FreeCAD main 3160daf1e2b6
// (LGPL-2.1-or-later): the Quantity.l lexer and Quantity.y grammar, Unit::getString
// and getTypeString, and UnitsSchema::translate with its special formatters.
// Values are in FreeCAD's internal units: mm, kg, s, A, K, mol, cd, degree.
import { UNITS, UNIT_TYPES, type Dims } from './units-data'
import { SCHEMAS as DATA } from './units-schemas'

export type Quantity = { value: number; dims: Dims }
/** The unit systems as UnitsApi::getDescriptions lists them: by number, the number UserSchema holds. */
export const SCHEMAS = [...DATA].sort((a, b) => a.num - b.num)
const ZERO: Dims = [0, 0, 0, 0, 0, 0, 0, 0]
const SYMBOLS = ['mm', 'kg', 's', 'A', 'K', 'mol', 'cd', 'deg']

type Tok = { t: string; v?: number; q?: Quantity }
const FUNCS: Record<string, (x: number) => number> = {
  acos: Math.acos, asin: Math.asin, atan: Math.atan, abs: Math.abs, exp: Math.exp, log: Math.log, log10: Math.log10,
  sin: Math.sin, sinh: Math.sinh, tan: Math.tan, tanh: Math.tanh, sqrt: Math.sqrt, cos: Math.cos,
}
// Tokens the lexer knows but the grammar never uses: they fail to parse.
const DEAD = ['atan2', 'mod', 'pow']
const WORDS = [...Object.keys(UNITS), ...Object.keys(FUNCS), ...DEAD, 'pi', 'e']
// Quantity.l's four number rules: {DIGIT}+"."?{DIGIT}*{EXPO}?, "."?{DIGIT}+{EXPO}?, and the same
// with a comma. So "3." and "1.e3" are numbers (strtod reads them as 3 and 1000).
const NUMBER = [/^\d+\.?\d*(?:[eE][-+]?\d+)?/, /^\.?\d+(?:[eE][-+]?\d+)?/, /^\d+,?\d*(?:[eE][-+]?\d+)?/, /^,?\d+(?:[eE][-+]?\d+)?/]
/** std::numeric_limits<double>::min(), what Quantity::parse returns for empty input. */
const DBL_MIN = 2.2250738585072014e-308

/** A parse failure ('syntax'), Base::UnitsMismatchError ('mismatch') or another evaluation error. */
export class QuantityError extends Error {
  constructor(message: string, readonly kind: 'syntax' | 'mismatch' | 'eval' = 'syntax') { super(message) }
}

/** Quantity.l: flex takes the longest match; on a tie the earlier rule (units first). */
function lex(text: string): Tok[] {
  const out: Tok[] = []
  let i = 0
  while (i < text.length) {
    const rest = text.slice(i), c = rest[0]
    if (c === '[') { const j = text.indexOf(']', i); if (j < 0) throw new QuantityError('Unterminated quantity comment'); i = j + 1; continue }
    if (/\s/.test(c)) { i++; continue }
    let best = '', tok: Tok | null = null
    for (const w of WORDS) {
      if (w.length > best.length && rest.startsWith(w)) {
        best = w
        tok = w in UNITS ? { t: 'UNIT', q: { value: UNITS[w][0], dims: UNITS[w][1] } }
          : w === 'pi' ? { t: 'NUM', v: Math.PI } : w === 'e' ? { t: 'NUM', v: Math.E } : { t: 'FN', v: WORDS.indexOf(w) }
        if (tok.t === 'FN') (tok as Tok & { name: string }).name = w
      }
    }
    for (const re of NUMBER) {
      const m = re.exec(rest)
      if (m && m[0].length > best.length) { best = m[0]; tok = { t: 'NUM', v: Number(m[0].replace(',', '.')) } }
    }
    if (best === '1') tok = { t: 'ONE', v: 1 }
    if (!tok) {
      if ('+()=/*^'.includes(c)) { best = c; tok = { t: c } }
      else if (c === '-' || c === '−') { best = c; tok = { t: '-' } }
      // The lexer's catch-all `.` returns the byte itself as a token. As a (signed) char, the
      // first byte of a non-ASCII character is negative, which bison takes for the end of the
      // input: the rest is ignored. Any other stray character is a syntax error.
      else if (c.charCodeAt(0) >= 0x80) break
      else throw new QuantityError('syntax error')
    }
    out.push(tok)
    i += best.length
  }
  return out
}

type Val = { kind: 'num' | 'unit' | 'quantity'; q: Quantity; one?: boolean }
const num = (v: number, one = false): Val => ({ kind: 'num', q: { value: v, dims: ZERO }, one })
/** Unit.h's checkRange(): each dimension's exponent must stay within ±unitExponentLimit (8). */
function checkRange(dims: Dims): Dims {
  for (const d of dims) {
    if (d >= 8) throw new QuantityError('Unit exponent overflow', 'eval')
    if (d < -8) throw new QuantityError('Unit exponent underflow', 'eval')
  }
  return dims
}
const mul = (a: Quantity, b: Quantity): Quantity => ({ value: a.value * b.value, dims: checkRange(a.dims.map((d, i) => d + b.dims[i]) as Dims) })
const div = (a: Quantity, b: Quantity): Quantity => ({ value: a.value / b.value, dims: checkRange(a.dims.map((d, i) => d - b.dims[i]) as Dims) })
/** Quantity::pow(const Quantity&), for `unit '^' num`: the value is raised to the exponent, the
 *  unit to static_cast<signed char>(exponent) — truncated, so "m^0.5" is a plain number. */
function pow(a: Quantity, e: number): Quantity {
  const n = (Math.trunc(e) << 24) >> 24
  return { value: Math.pow(a.value, e), dims: checkRange(a.dims.map((d) => d * n) as Dims) }
}
const sameDims = (a: Dims, b: Dims) => a.every((d, i) => d === b[i])

/** Quantity.y: input is a number, a unit, or up to three quantities added (num unit, num / unit). */
export function parseQuantity(text: string): Quantity {
  const toks = lex(text)
  if (!toks.length) return { value: DBL_MIN, dims: ZERO }
  let p = 0
  const peek = () => toks[p]
  const eat = (t: string) => { if (toks[p]?.t !== t) throw new QuantityError('syntax error'); return toks[p++] }
  const startsUnit = (k = p): boolean => toks[k]?.t === 'UNIT' || (toks[k]?.t === '(' && startsUnit(k + 1)) || (toks[k]?.t === 'ONE' && toks[k + 1]?.t === '/' && startsUnit(k + 2))

  // num: NUM | ONE | num (+ - * /) num | (+ -) num | num ^ num | ( num ) | FUNC ( num )
  const PREC: Record<string, number> = { '+': 1, '-': 1, '*': 2, '/': 2, '^': 4 }
  function numPrimary(): Val {
    const t = peek()
    if (!t) throw new QuantityError('syntax error')
    if (t.t === 'NUM') { p++; return num(t.v!) }
    if (t.t === 'ONE') { p++; return num(1, true) }
    if (t.t === '+' || t.t === '-') { p++; const v = numExpr(3); return num(t.t === '-' ? -v.q.value : v.q.value) }
    if (t.t === '(') { p++; const v = numExpr(0); eat(')'); return v }
    if (t.t === 'FN') {
      const name = (t as Tok & { name: string }).name
      if (!(name in FUNCS)) throw new QuantityError('syntax error')
      p++; eat('('); const v = numExpr(0); eat(')')
      return num(FUNCS[name](v.q.value))
    }
    throw new QuantityError('syntax error')
  }
  function numExpr(min: number): Val {
    let left = numPrimary()
    for (;;) {
      const t = peek()
      if (!t || !(t.t in PREC) || PREC[t.t] < min) return left
      if (t.t === '/' && startsUnit(p + 1)) return left // num '/' unit: a quantity, one level up
      p++
      const right = numExpr(t.t === '^' ? PREC[t.t] : PREC[t.t] + 1)
      const a = left.q.value, b = right.q.value
      left = num(t.t === '+' ? a + b : t.t === '-' ? a - b : t.t === '*' ? a * b : t.t === '/' ? a / b : Math.pow(a, b))
    }
  }
  // unit: UNIT | ONE / unit | unit * unit | unit / unit | unit ^ num | ( unit )
  function unitPrimary(): Quantity {
    const t = peek()
    if (t?.t === 'UNIT') { p++; return t.q! }
    if (t?.t === 'ONE' && toks[p + 1]?.t === '/') { p += 2; return div({ value: 1, dims: ZERO }, unitExpr(3)) }
    if (t?.t === '(') { p++; const u = unitExpr(0); eat(')'); return u }
    throw new QuantityError('syntax error')
  }
  function unitExpr(min: number): Quantity {
    let left = unitPrimary()
    for (;;) {
      const t = peek()
      if (!t) return left
      if (t.t === '^' && 4 >= min) { p++; left = pow(left, numExpr(4).q.value); continue }
      if ((t.t === '*' || t.t === '/') && 2 >= min && startsUnit(p + 1)) { p++; const r = unitExpr(3); left = t.t === '*' ? mul(left, r) : div(left, r); continue }
      return left
    }
  }
  function quantity(): Val {
    if (startsUnit()) return { kind: 'unit', q: unitExpr(0) }
    const n = numExpr(0)
    if (!peek()) return n
    if (peek().t === '/' && startsUnit(p + 1)) { p++; return { kind: 'quantity', q: div(n.q, unitExpr(0)) } }
    if (startsUnit()) return { kind: 'quantity', q: mul(n.q, unitExpr(0)) }
    throw new QuantityError('syntax error')
  }
  const first = quantity()
  if (first.kind !== 'quantity') { if (p < toks.length) throw new QuantityError('syntax error'); return first.q }
  let sum = first.q
  for (let k = 1; k < 3 && p < toks.length; k++) {
    const next = quantity()
    if (next.kind !== 'quantity') throw new QuantityError('syntax error')
    if (!sameDims(sum.dims, next.q.dims)) throw new QuantityError('Quantity::operator +(): Unit mismatch in plus operation', 'mismatch')
    sum = { value: sum.value + next.q.value, dims: sum.dims }
  }
  if (p < toks.length) throw new QuantityError('syntax error')
  return sum
}

/** Unit::getTypeString: the name of the quantity type, or ''. */
export const typeString = (dims: Dims) => UNIT_TYPES.find(([, d]) => sameDims(d, dims))?.[0] ?? ''
/** Unit::getString: mm^2, kg/(mm*s^2), 1/mm. */
export function unitString(dims: Dims): string {
  const part = (i: number) => (Math.abs(dims[i]) <= 1 ? SYMBOLS[i] : `${SYMBOLS[i]}^${Math.abs(dims[i])}`)
  const pos = dims.map((d, i) => (d > 0 ? i : -1)).filter((i) => i >= 0), neg = dims.map((d, i) => (d < 0 ? i : -1)).filter((i) => i >= 0)
  const numr = pos.map(part).join('*')
  if (!neg.length) return numr
  const den = neg.map(part).join('*')
  return `${numr || '1'}/${neg.length > 1 ? `(${den})` : den}`
}

/** toFractional: feet, inches and fractions of an inch, for Building US. */
function toFractional(value: number, denominator: number) {
  let n = Math.round((Math.abs(value) / 25.4) * denominator)
  if (n === 0) return '0'
  const feet = Math.floor(n / (12 * denominator))
  n -= 12 * denominator * feet
  const inches = Math.floor(n / denominator)
  let numerator = n - denominator * inches
  const gcd = (a: number, b: number): number => (b === 0 ? a : gcd(b, a % b))
  const g = gcd(numerator, denominator)
  numerator /= g
  const den = denominator / g
  let out = value < 0 ? '-' : '', space = false
  if (feet > 0) { out += `${feet}'`; space = true }
  if (inches > 0) { out += `${space ? ' ' : ''}${inches}"`; space = false }
  if (numerator > 0) { if (inches > 0) { out += ` ${value < 0 ? '-' : '+'} `; space = false } out += `${space ? ' ' : ''}${numerator}/${den}"` }
  return out
}
/** toDms: degrees, minutes and seconds. */
function toDms(value: number) {
  const split = (t: number): [number, number] => { const w = Math.floor(t); return [w, 60 * (t - w)] }
  const [deg, mins] = split(value)
  let out = `${deg}°`
  if (mins > 0) { const [m, secs] = split(mins); out += `${m}′`; if (secs > 0) out += `${Math.round(secs)}″` }
  return out
}

/** UnitsApi's current schema, decimals and fraction denominator (Preferences > General > Units). */
export const unitPrefs = { schema: 0, decimals: 2, denominator: 8 }

/** TaskMassProperties.cpp:1210-1228 (setText lambda): format a mass property value
 *  in internal units. If |value| < 1e-7 (Base::Precision::Confusion), becomes "0.00 unit". */
export function formatMassProperty(value: number, dims: Dims, schema = unitPrefs.schema, decimals = unitPrefs.decimals, denominator = unitPrefs.denominator): string {
  const q: Quantity = { value: Math.abs(value) < 1e-7 ? 0 : value, dims }
  return userString(q, schema, decimals, denominator).text
}

/** `digits` (value = d0.d1d2… × 10^exp) rounded half to even at `decimals` fraction digits,
 *  scaled by 10^decimals. */
function roundHalfEven(digits: string, exp: number, decimals: number): bigint {
  const keep = exp + 1 + decimals // digits left of the rounding place
  if (keep >= digits.length) return BigInt(digits) * 10n ** BigInt(keep - digits.length)
  if (keep < 0) return 0n
  let n = keep ? BigInt(digits.slice(0, keep)) : 0n
  const next = digits[keep], rest = digits.slice(keep + 1)
  if (next > '5' || (next === '5' && (/[1-9]/.test(rest) || n % 2n === 1n))) n += 1n
  return n
}
/** n / 10^decimals written out: "1234" with 2 → "12.34". */
function pointed(n: bigint, decimals: number): string {
  const t = n.toString().padStart(decimals + 1, '0')
  return decimals ? `${t.slice(0, -decimals)}.${t.slice(-decimals)}` : t
}
/** The shortest decimal digits that read back as the same double (what ICU formats from). */
function shortestDigits(v: number): { digits: string; exp: number } {
  const [m, e] = Math.abs(v).toExponential().split('e')
  return { digits: m.replace('.', ''), exp: Number(e) }
}
/** A double's exact decimal digits (what printf rounds): m × 2^p, written out with BigInt. */
function exactDigits(v: number): { digits: string; exp: number } {
  if (v === 0) return { digits: '0', exp: 0 }
  const view = new DataView(new ArrayBuffer(8))
  view.setFloat64(0, Math.abs(v))
  const hi = view.getUint32(0), lo = view.getUint32(4), e = (hi >>> 20) & 0x7ff
  let m = (BigInt(hi & 0xfffff) << 32n) | BigInt(lo), p = -1074
  if (e) { m |= 1n << 52n; p = e - 1075 }
  const s = p >= 0 ? (m << BigInt(p)).toString() : (m * 5n ** BigInt(-p)).toString()
  return { digits: s.replace(/0+$/, '') || '0', exp: s.length - 1 - (p >= 0 ? 0 : -p) }
}
const sign = (v: number) => (v < 0 || Object.is(v, -0) ? '-' : '')

/** Base::formatNumericValue with QuantityFormat::Fixed (NumericFormatting.cpp): ICU's DecimalFormat
 *  with `decimals` fraction digits and no grouping (OmitGroupSeparator), in the en_US_POSIX
 *  fallback locale. ICU rounds the double's shortest round-trip decimal digits, half to even —
 *  so 9.995 shows as 10.00 and 0.5 as 0 — and keeps the minus sign on negative zero and on
 *  negative numbers that round to zero. */
export function formatFixed(v: number, decimals: number): string {
  if (!Number.isFinite(v)) return String(v)
  const { digits, exp } = shortestDigits(v)
  return sign(v) + pointed(roundHalfEven(digits, exp, decimals), decimals)
}

/** Quantity::toNumber: a std::stringstream at setprecision(precision), std::fixed for Fixed and the
 *  default float format for Default — printf's %.*f and %.*g, of the double's exact binary value,
 *  ties to even. */
export function toNumber(v: number, format: 'Fixed' | 'Default', precision: number): string {
  if (!Number.isFinite(v)) return Number.isNaN(v) ? 'nan' : v < 0 ? '-inf' : 'inf'
  const { digits, exp } = exactDigits(v)
  if (format === 'Fixed') return sign(v) + pointed(roundHalfEven(digits, exp, precision), precision)
  // %g: P significant digits; style f with P - 1 - X decimals if P > X >= -4, where X is the
  // exponent of the value rounded to P digits, else style e; trailing zeros removed.
  const P = precision || 1
  const n = roundHalfEven(digits, exp, P - 1 - exp)
  const X = n.toString().length > P ? exp + 1 : exp
  const trim = (t: string) => (t.includes('.') ? t.replace(/0+$/, '').replace(/\.$/, '') : t)
  if (P > X && X >= -4) return sign(v) + trim(pointed(roundHalfEven(digits, exp, P - 1 - X), P - 1 - X))
  const m = n.toString().slice(0, P)
  return `${sign(v)}${trim(m[0] + (P > 1 ? '.' + m.slice(1) : ''))}e${X < 0 ? '-' : '+'}${String(Math.abs(X)).padStart(2, '0')}`
}

/** UnitsSchema::translate: the quantity as the schema shows it, e.g. "12.50 mm" or "1.25 m".
 *  Returns the text, and the factor and unit it used. */
export function userString(q: Quantity, schema = unitPrefs.schema, decimals = unitPrefs.decimals, denominator = unitPrefs.denominator): { text: string; factor: number; unit: string } {
  // UnitsSchemas::findSpec throws "UnitSchemaSpec not found" for an unknown schema number;
  // kept as a silent fallback here since `schema` is a runtime value from outside this file's
  // ownership (only the UI's own dropdown ever supplies it, and it never offers a bad id).
  const spec = SCHEMAS.find((s) => s.num === schema) ?? SCHEMAS[0]
  let factor = 1, unit = unitString(q.dims)
  const rows = spec.specs[typeString(q.dims)]
  if (rows) {
    const mag = Math.abs(q.value)
    const row = rows.find(([th]) => th * (1 - 1e-12) > mag || th === 0)
    // UnitsSchema::translate: every real spec ends in a threshold-0 catch-all row, so this is
    // unreachable today; throwing (instead of silently falling through) matches the source.
    if (!row) throw new QuantityError(`Suitable threshold not found. Schema: ${spec.name} value: ${q.value}`, 'eval')
    if (row[2] === 0) {
      if (row[1] === 'toFractional') return { text: toFractional(q.value, denominator), factor: 25.4, unit: 'in' }
      if (row[1] === 'toDMS') return { text: toDms(q.value), factor: 1, unit: 'deg' }
    } else { factor = row[2]; unit = row[1] }
  }
  const v = q.value / factor
  const s = formatFixed(v, decimals)
  const bare = !unit || ['°', '″', '′', '"', "'"].includes(unit)
  return { text: `${s}${bare ? '' : ' '}${unit}`, factor, unit }
}
