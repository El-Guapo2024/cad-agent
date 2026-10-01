// FreeCAD's expressions (App/ExpressionParser), the part the property editor and the
// quantity boxes need: + - * / % ^, comparisons (== != < > <= >=) and the a?b:c conditional,
// units (a number's unit binds tighter than * and /, so "10 mm^2" is ten square millimetres),
// the part's other parameters by name, pi and e, and FreeCAD's functions. Trigonometric
// functions take and give degrees, as FreeCAD's do. Units must agree for + and -, as FreeCAD
// requires. Parsed to a tree first, so a quantity box can give its unit to the bare numbers in
// a sum (App/QuantityInput.cpp).
import { UNITS, type Dims } from './units-data'
import { QuantityError, type Quantity } from './quantity'

const ZERO: Dims = [0, 0, 0, 0, 0, 0, 0, 0]
const ANGLE: Dims = [0, 0, 0, 0, 0, 0, 0, 1]
const same = (a: Dims, b: Dims) => a.every((d, i) => d === b[i])
const plain = (v: number): Quantity => ({ value: v, dims: ZERO })
const deg = (r: number) => (r * 180) / Math.PI, rad = (q: Quantity) => (q.value * Math.PI) / 180
/** asBool (App/Expression.cpp): anything but (near) zero. */
const truthy = (q: Quantity) => Math.abs(q.value) >= 1e-7
/** Collector (App/Expression.cpp): every argument must share the first argument's unit. */
function sameUnit(xs: Quantity[]) {
  for (let i = 1; i < xs.length; i++) if (!same(xs[i].dims, xs[0].dims)) throw new QuantityError('Units must be equal.', 'mismatch')
}
/** FunctionExpression's POW case and Unit::pow(): the exponent must be dimensionless, and
 *  when the base has a unit each resulting dimension must be (near-)integer. */
function powOp(a: Quantity, b: Quantity): Quantity {
  if (!same(b.dims, ZERO)) throw new QuantityError('Exponent is not allowed to have a unit.', 'eval')
  if (same(a.dims, ZERO)) return { value: Math.pow(a.value, b.value), dims: ZERO }
  const dims = a.dims.map((d) => d * b.value)
  if (dims.some((d) => Math.abs(Math.round(d) - d) >= Number.EPSILON)) throw new QuantityError('Exponent must be an integer when used with a unit.', 'eval')
  return { value: Math.pow(a.value, b.value), dims: dims.map((d) => Math.round(d)) as Dims }
}
/** Unit::sqrt()/cbrt() via Unit::root(num): each dimension must be evenly divisible by num. */
function root(a: Quantity, n: 2 | 3): Quantity {
  const dims = a.dims.map((d) => {
    if (d % n !== 0) throw new QuantityError('unit values must be divisible by root', 'eval')
    return d / n
  }) as Dims
  return { value: n === 2 ? Math.sqrt(a.value) : Math.cbrt(a.value), dims }
}

/** FreeCAD's expression functions over unitless numbers or angles (in degrees). */
const FUNCS: Record<string, (args: Quantity[]) => Quantity> = {
  abs: ([a]) => ({ ...a, value: Math.abs(a.value) }),
  sqrt: ([a]) => root(a, 2),
  cbrt: ([a]) => root(a, 3),
  sin: ([a]) => plain(Math.sin(rad(a))), cos: ([a]) => plain(Math.cos(rad(a))), tan: ([a]) => plain(Math.tan(rad(a))),
  asin: ([a]) => ({ value: deg(Math.asin(a.value)), dims: ANGLE }), acos: ([a]) => ({ value: deg(Math.acos(a.value)), dims: ANGLE }),
  atan: ([a]) => ({ value: deg(Math.atan(a.value)), dims: ANGLE }), atan2: ([y, x]) => ({ value: deg(Math.atan2(y.value, x.value)), dims: ANGLE }),
  sinh: ([a]) => plain(Math.sinh(a.value)), cosh: ([a]) => plain(Math.cosh(a.value)), tanh: ([a]) => plain(Math.tanh(a.value)),
  exp: ([a]) => plain(Math.exp(a.value)), log: ([a]) => plain(Math.log(a.value)), log10: ([a]) => plain(Math.log10(a.value)),
  pow: ([a, b]) => powOp(a, b),
  round: ([a]) => ({ ...a, value: Math.round(a.value) }), trunc: ([a]) => ({ ...a, value: Math.trunc(a.value) }),
  floor: ([a]) => ({ ...a, value: Math.floor(a.value) }), ceil: ([a]) => ({ ...a, value: Math.ceil(a.value) }),
  mod: ([a, b]) => ({ ...a, value: a.value % b.value }),
  hypot: (xs) => { sameUnit(xs); return { value: Math.hypot(...xs.map((x) => x.value)), dims: xs[0].dims } },
  cath: (xs) => { sameUnit(xs); return { value: Math.sqrt(xs.reduce((t, x, i) => t + (i ? -1 : 1) * x.value ** 2, 0)), dims: xs[0].dims } },
  min: (xs) => { sameUnit(xs); return xs.reduce((m, x) => (x.value < m.value ? x : m)) },
  max: (xs) => { sameUnit(xs); return xs.reduce((m, x) => (x.value > m.value ? x : m)) },
  sum: (xs) => { sameUnit(xs); return { value: xs.reduce((t, x) => t + x.value, 0), dims: xs[0].dims } },
  average: (xs) => { sameUnit(xs); return { value: xs.reduce((t, x) => t + x.value, 0) / xs.length, dims: xs[0].dims } },
  stddev: (xs) => {
    if (xs.length < 2) throw new QuantityError('Invalid number of entries: at least two required.', 'eval')
    sameUnit(xs)
    const mean = xs.reduce((t, x) => t + x.value, 0) / xs.length
    const variance = xs.reduce((t, x) => t + (x.value - mean) ** 2, 0) / (xs.length - 1)
    return { value: Math.sqrt(variance), dims: xs[0].dims }
  },
  count: (xs) => plain(xs.length),
  and: (xs) => plain(xs.every(truthy) ? 1 : 0),
  or: (xs) => plain(xs.some(truthy) ? 1 : 0),
  not: ([a]) => plain(truthy(a) ? 0 : 1),
}
const UNIT_KEYS = Object.keys(UNITS).sort((a, b) => b.length - a.length)

/** The expression tree (NumberExpression, UnitExpression, OperatorExpression,
 *  FunctionExpression, ConditionalExpression). */
export type Node =
  | { k: 'num'; v: number }
  | { k: 'unit'; q: Quantity }
  | { k: 'name'; s: string }
  | { k: 'op'; op: '+' | '-' | '*' | '/' | '%' | '^' | 'unit' | '==' | '!=' | '<' | '>' | '<=' | '>='; l: Node; r: Node }
  | { k: 'neg'; a: Node }
  | { k: 'fn'; s: string; args: Node[] }
  | { k: 'cond'; c: Node; t: Node; f: Node }

type Tok = { t: 'num' | 'id' | 'op'; s: string; v?: number }
function lex(text: string): Tok[] {
  const out: Tok[] = []
  let i = 0
  while (i < text.length) {
    const rest = text.slice(i)
    if (/^\s/.test(rest)) { i++; continue }
    // {DIGIT}*"."{DIGIT}+{EXPO}? | {DIGIT}*","{DIGIT}+{EXPO}? | {DIGIT}+{EXPO}? (Expression.l):
    // a decimal point or comma must be followed by at least one digit, so a lone trailing
    // separator ("3.") is not a complete number.
    const n = /^(\d+\.\d+|\.\d+|\d+,\d+|,\d+|\d+)([eE][-+]?\d+)?/.exec(rest)
    if (n) { out.push({ t: 'num', s: n[0], v: Number(n[0].replace(',', '.')) }); i += n[0].length; continue }
    const id = /^[A-Za-z_µ][A-Za-z0-9_]*/.exec(rest)
    if (id) { out.push({ t: 'id', s: id[0] }); i += id[0].length; continue }
    const u = UNIT_KEYS.find((k) => !/^[A-Za-z]/.test(k) && rest.startsWith(k)) // °, ″, ′, " and '
    if (u) { out.push({ t: 'id', s: u }); i += u.length; continue }
    const two = rest.slice(0, 2)
    if (two === '==' || two === '!=' || two === '<=' || two === '>=') { out.push({ t: 'op', s: two }); i += 2; continue }
    // ';' is the alternate function-argument separator (App/Expression.y's "args ';' exp"),
    // needed once ',' can also start a decimal number: "hypot(1,2)" is one argument (1.2);
    // "hypot(1;2)" (or "hypot(1, 2)", with a space) is two.
    if ('+-*/%^(),<>?:;'.includes(rest[0])) { out.push({ t: 'op', s: rest[0] }); i++; continue }
    if (rest[0] === '−') { out.push({ t: 'op', s: '-' }); i++; continue }
    throw new QuantityError(`unexpected '${rest[0]}'`)
  }
  return out
}

/** Parse an expression (without its leading "="). `names` are the variables it may use;
 *  a unit's name used as a variable means the variable. */
export function parseExpr(text: string, names: Set<string> = new Set()): Node {
  const toks = lex(text)
  let p = 0
  const isOp = (s: string, k = p) => toks[k]?.t === 'op' && toks[k].s === s
  const eat = (s: string) => { if (!isOp(s)) throw new QuantityError(`expected '${s}'`); p++ }
  const isUnit = (k = p) => toks[k]?.t === 'id' && toks[k].s in UNITS && !names.has(toks[k].s) && !(toks[k].s in FUNCS)
  const unitLeaf = (s: string): Node => ({ k: 'unit', q: { value: UNITS[s][0], dims: UNITS[s][1] } })
  // Expression.y precedence, loosest to tightest: %right '?' ':'; %left EQ NEQ LT GT GTE LTE;
  // %left MINUSSIGN '+'; %left '*' '/' '%'; NUM_AND_UNIT; %left '^'; %precedence NEG; POS.
  /** exp '?' exp ':' exp, %right (lowest precedence): right-associative, so "a?b:c?d:e" is
   *  "a?b:(c?d:e)". */
  function ternary(): Node {
    const c = cmp()
    if (isOp('?')) { p++; const t = ternary(); eat(':'); const f = ternary(); return { k: 'cond', c, t, f } }
    return c
  }
  /** exp (EQ|NEQ|LT|GT|LTE|GTE) exp, %left, one tier below +/-. */
  function cmp(): Node {
    let l = expr()
    while (isOp('==') || isOp('!=') || isOp('<') || isOp('>') || isOp('<=') || isOp('>=')) {
      const op = toks[p++].s as '==' | '!=' | '<' | '>' | '<=' | '>='
      l = { k: 'op', op, l, r: expr() }
    }
    return l
  }
  function expr(): Node {
    let l = term()
    while (isOp('+') || isOp('-')) { const op = toks[p++].s as '+' | '-'; l = { k: 'op', op, l, r: term() } }
    return l
  }
  function term(): Node {
    let l = factor()
    while (isOp('*') || isOp('/') || isOp('%')) { const op = toks[p++].s as '*' | '/' | '%'; l = { k: 'op', op, l, r: factor() } }
    return l
  }
  /** exp '^' exp, %left (App/Expression.y): left-associative, so "2^3^2" is (2^3)^2, not
   *  2^(3^2). */
  function factor(): Node {
    let base = unary()
    while (isOp('^')) { p++; base = { k: 'op', op: '^', l: base, r: unary() } }
    return base
  }
  function unary(): Node {
    if (isOp('-')) { p++; return { k: 'neg', a: unary() } }
    if (isOp('+')) { p++; return unary() }
    return postfix()
  }
  /** unit_exp: a unit, times or over another unit, or to an integer power. */
  function unitExp(): Node {
    let u = unitLeaf(toks[p++].s)
    for (;;) {
      if ((isOp('*') || isOp('/')) && isUnit(p + 1)) { const op = toks[p++].s as '*' | '/'; u = { k: 'op', op, l: u, r: unitLeaf(toks[p++].s) }; continue }
      if (isOp('^') && (toks[p + 1]?.t === 'num' || (isOp('-', p + 1) && toks[p + 2]?.t === 'num'))) {
        p++
        const neg = isOp('-') ? (p++, -1) : 1
        u = { k: 'op', op: '^', l: u, r: { k: 'num', v: neg * toks[p++].v! } }
        continue
      }
      return u
    }
  }
  /** A number or a bracket may carry a unit right after it: 10 mm, 2 in, (1 + 2) cm. A bare
   *  number may also carry two building units with no operator between them: 5' 3" is 5 feet
   *  3 inches (App/Expression.y's "num us_building_unit num us_building_unit" — ' and " only,
   *  not "ft"/"in"). */
  function postfix(): Node {
    const v = primary()
    if (isUnit() && (v.k === 'num' || v.k === 'op' || v.k === 'neg' || v.k === 'name' || v.k === 'fn')) {
      const firstUnitTok = toks[p].s
      const r = unitExp()
      let u: Node = { k: 'op', op: 'unit', l: v, r }
      if (v.k === 'num' && r.k === 'unit' && (firstUnitTok === "'" || firstUnitTok === '"') &&
          toks[p]?.t === 'num' && isUnit(p + 1) && (toks[p + 1].s === "'" || toks[p + 1].s === '"')) {
        const n2: Node = { k: 'num', v: toks[p++].v! }
        const u2 = unitLeaf(toks[p++].s)
        u = { k: 'op', op: '+', l: u, r: { k: 'op', op: 'unit', l: n2, r: u2 } }
      }
      return u
    }
    return v
  }
  function primary(): Node {
    const t = toks[p]
    if (!t) throw new QuantityError('unexpected end')
    if (t.t === 'num') { p++; return { k: 'num', v: t.v! } }
    if (isOp('(')) { p++; const v = ternary(); eat(')'); return v }
    if (t.t === 'id') {
      if (t.s in FUNCS && isOp('(', p + 1)) {
        p += 2
        const args: Node[] = []
        if (!isOp(')')) { args.push(ternary()); while (isOp(',') || isOp(';')) { p++; args.push(ternary()) } }
        eat(')')
        return { k: 'fn', s: t.s, args }
      }
      if (isUnit()) return unitExp()
      p++
      return { k: 'name', s: t.s }
    }
    throw new QuantityError(`unexpected '${t.s}'`)
  }
  const v = ternary()
  if (p < toks.length) throw new QuantityError(`unexpected '${toks[p].s}'`)
  return v
}

/** Evaluate a tree; `vars` are the names it may use. */
export function evalNode(n: Node, vars: Record<string, Quantity>): Quantity {
  const mul = (a: Quantity, b: Quantity, inv = false): Quantity =>
    ({ value: inv ? a.value / b.value : a.value * b.value, dims: a.dims.map((d, i) => d + (inv ? -b.dims[i] : b.dims[i])) as Dims })
  switch (n.k) {
    case 'num': return plain(n.v)
    case 'unit': return n.q
    case 'neg': { const a = evalNode(n.a, vars); return { ...a, value: -a.value } }
    case 'name':
      if (n.s in vars) return vars[n.s]
      if (n.s === 'pi') return plain(Math.PI)
      if (n.s === 'e') return plain(Math.E)
      // Expression.l CONSTANT: None/False are 0, True is 1.
      if (n.s === 'None' || n.s === 'False') return plain(0)
      if (n.s === 'True') return plain(1)
      throw new QuantityError(`unknown name '${n.s}'`, 'eval')
    case 'fn': return FUNCS[n.s](n.args.map((a) => evalNode(a, vars)))
    // ConditionalExpression::_getPyValue: only the taken branch is evaluated.
    case 'cond': return truthy(evalNode(n.c, vars)) ? evalNode(n.t, vars) : evalNode(n.f, vars)
    case 'op': {
      const a = evalNode(n.l, vars), b = evalNode(n.r, vars)
      switch (n.op) {
        case '+': case '-':
          if (!same(a.dims, b.dims)) throw new QuantityError(`Quantity::operator ${n.op}(): Unit mismatch in ${n.op === '+' ? 'plus' : 'minus'} operation`, 'mismatch')
          return { value: n.op === '+' ? a.value + b.value : a.value - b.value, dims: a.dims }
        case '*': case 'unit': return mul(a, b)
        case '/': return mul(a, b, true)
        case '%': return { value: a.value % b.value, dims: a.dims }
        case '^': return powOp(a, b)
        // OperatorExpression EQ/NEQ (Quantity::operator==): no unit-mismatch throw, just false.
        case '==': return plain(a.value === b.value && same(a.dims, b.dims) ? 1 : 0)
        case '!=': return plain(a.value === b.value && same(a.dims, b.dims) ? 0 : 1)
        // LT/GT/LTE/GTE (Quantity::operator<, etc.): throw on unit mismatch.
        case '<': case '>': case '<=': case '>=':
          if (!same(a.dims, b.dims)) throw new QuantityError(`Quantity::operator ${n.op}(): quantities need to have same unit to compare`, 'mismatch')
          return plain((n.op === '<' ? a.value < b.value : n.op === '>' ? a.value > b.value : n.op === '<=' ? a.value <= b.value : a.value >= b.value) ? 1 : 0)
      }
    }
  }
}

/** Evaluate an expression (without its leading "="); `vars` are the names it may use. */
export function evaluate(text: string, vars: Record<string, Quantity>): Quantity {
  return evalNode(parseExpr(text, new Set(Object.keys(vars))), vars)
}

/** AdditiveOperatorDetector: whether the input has a + or - between terms. */
export function hasAdditive(n: Node): boolean {
  if (n.k === 'op') return n.op === '+' || n.op === '-' || hasAdditive(n.l) || hasAdditive(n.r)
  if (n.k === 'neg') return hasAdditive(n.a)
  if (n.k === 'fn') return n.args.some(hasAdditive)
  // ConditionalExpression::_visit recurses into all three of condition/trueExpr/falseExpr.
  if (n.k === 'cond') return hasAdditive(n.c) || hasAdditive(n.t) || hasAdditive(n.f)
  return false
}

/** rewriteOwnerlessQuantityExpression: in a quantity field "1/2 mm" means (1/2) mm. */
export function rewriteOwnerless(n: Node): Node {
  if (n.k !== 'op') return n
  const l = rewriteOwnerless(n.l), r = rewriteOwnerless(n.r)
  if (n.op === '/' && r.k === 'op' && r.op === 'unit') return { k: 'op', op: '*', l: { k: 'op', op: '/', l, r: r.l }, r: r.r }
  return { ...n, l, r }
}

/** applyDefaultUnitPolicy: at each + or - from the top, a whole term without a unit takes
 *  the field's unit; units, products and powers keep their own meaning. */
export function applyDefaultUnit(n: Node, unit: Quantity, vars: Record<string, Quantity> = {}): Node {
  if (n.k !== 'op' || (n.op !== '+' && n.op !== '-')) return n
  const side = (o: Node): Node => {
    try {
      const q = evalNode(o, vars)
      if (same(q.dims, ZERO)) return { k: 'op', op: 'unit', l: o, r: { k: 'unit', q: unit } }
    } catch { /* a nested sum may need its own terms given the unit first */ }
    return o.k === 'op' && (o.op === '+' || o.op === '-') ? applyDefaultUnit(o, unit, vars) : o
  }
  return { ...n, l: side(n.l), r: side(n.r) }
}
