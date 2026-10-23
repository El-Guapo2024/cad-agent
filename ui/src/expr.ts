// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/App/Expression.cpp: 2015 Eivind Kvedalen
//   src/App/Expression.l: 2010 Jürgen Riegel; 2015 Eivind Kvedalen
//   src/App/Expression.y: 2010 Jürgen Riegel; 2015 Eivind Kvedalen
//   src/App/ObjectIdentifier.cpp: 2015 Eivind Kvedalen
//   src/Base/Tools.h: 2009 Werner Mayer
//   src/Base/Vector3D.cpp: 2005 Imetric 3D GmbH
//   No copyright line in the file: src/App/QuantityInput.cpp
// FreeCAD's expression language (App/Expression.l, Expression.y, Expression.cpp at FreeCAD main 3160daf1e2b6): the lexer, the
// grammar's tables (expr-grammar.ts, made from Expression.y), the expression classes with their toString (the text of an
// error says which part of the expression failed), and their evaluation, which like FreeCAD's runs on Python's values and
// rules (expr-py.ts). scripts/exprdiff.py runs some 70,000 expressions through this and through the real FreeCAD.
// Part parameters take the place of the owning object's properties; a parameter named like a unit or constant shadows it
// (FreeCAD cannot name such a property, a part here can).
import { UNITS } from './units-data'
import { parseQuantity, toNumber, QuantityError, type Quantity } from './quantity'
import { RULES, STATES, TERMINALS } from './expr-grammar'
import * as P from './expr-py'
import { PyError, type PyVal } from './expr-py'
import type { Dims } from './units-data'

export { PyError, type PyVal }
const ZERO = P.ZERO

// ─── The tree (NumberExpression, UnitExpression, OperatorExpression, FunctionExpression ...) ─────────────────────

export type BinOpName = '+' | '-' | '*' | '/' | '%' | '^' | '==' | '!=' | '<' | '>' | '<=' | '>=' | 'unit'
/** ObjectIdentifier's components after the property: an attribute, an index, a key or a range (begin, end or null, step). */
export type IdComp =
  | { k: 'attr'; name: string }
  | { k: 'array'; i: number }
  | { k: 'map'; key: string }
  | { k: 'range'; b: number; e: number | null; s: number }
/** Expression::Component: a[e1], a[e1:e2:e3] or .name, for what the identifier could not hold. */
export type ExprComp = { name: string } | { e1: Node | null; e2: Node | null; e3: Node | null; range: boolean }
/** A name as the grammar reads it: where it says the document and object, or leaves them to the owner. */
export type Ref = { name: string; str: boolean }
export type VarPath = {
  /** the document and object the text names (`Doc#Obj.prop`, `Obj.<<sub>>.prop`); null when it leaves them to the owner. */
  doc: Ref | null
  obj: Ref | null
  /** a leading '.': the owner's own property. */
  local: boolean
  /** the property, then the attributes the grammar gave as `.name` (`pLen.Value`). */
  names: string[]
  /** components that ObjectIdentifier holds: attributes after the property, constant indices and ranges. */
  sub: IdComp[]
}
export type Node =
  | { k: 'num'; v: number }
  | { k: 'const'; name: 'pi' | 'e' | 'None' | 'True' | 'False'; v: number }
  | { k: 'unit'; q: Quantity; s: string }
  | { k: 'str'; s: string; bad?: string }
  | { k: 'var'; path: VarPath; comps: ExprComp[] }
  | { k: 'neg'; a: Node }
  | { k: 'pos'; a: Node }
  | { k: 'op'; op: BinOpName; l: Node; r: Node }
  | { k: 'fn'; f: string; name: string; args: Node[] }
  | { k: 'cond'; c: Node; t: Node; f: Node }
  | { k: 'range'; a: string; b: string }

/** The error ParserExpression throws for a text it cannot read. */
export const parseError = (text: string) => new PyError(`Failed to parse expression '${text}'`, 'ParserError', 'syntax')

// ─── The lexer (Expression.l) ──────────────────────────────────────────────────────────────────────

const TERM = new Map(TERMINALS.map((t, i) => [t, i]))
const T = (name: string) => TERM.get(name) ?? -1
const UNIT_TOKENS = Object.keys(UNITS).sort((a, b) => b.length - a.length)
const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const RE_UNIT = new RegExp(UNIT_TOKENS.map(escapeRe).join('|'), 'y')
const RE_WS = /[ \t]+/y
const RE_NL = /\n/y
const RE_STRING = /<<(?:\\[\s\S]|[^\\>\n])*>>/y
const RE_CHAR = /[%+()=/*^,.{}[\]:;@?#]/y
const RE_N1 = /[0-9]*\.[0-9]+(?:[eE][-+]?[0-9]+)?/y
const RE_N2 = /[0-9]*,[0-9]+(?:[eE][-+]?[0-9]+)?/y
const RE_N3 = /[0-9]+[eE][-+]?[0-9]+/y
const RE_N4 = /[0-9]+/y
const RE_CONST = /None|True|true|False|false|pi|e/y
const RE_CELL1 = /\$[A-Za-z]+\$[0-9]+/y
const RE_CELL2 = /[A-Za-z]{1,2}\$[0-9]+/y
const RE_CELL3 = /\$[A-Za-z]{1,2}[0-9]+/y
// A function name: a letter first, no '_', no '@', then optional blanks (Expression.l's [\20\t]: a tab, or the byte 16, not a space).
const RE_FUNC = /\p{L}\p{M}*(?:\p{L}\p{M}*|\p{N}|_)*[\x10\t]*\(/yu
const RE_IDENT = /(?:\p{L}\p{M}*|_)(?:\p{L}\p{M}*|\p{N}|_|@)*/yu
const SIMPLE_OPS = ['==', '!=', '>=', '<=', '>', '<']

/** The function names Expression.y's lexer registers (initParser). */
const FUNCTIONS = new Set(['abs', 'acos', 'asin', 'atan', 'atan2', 'cath', 'cbrt', 'ceil', 'cos', 'cosh', 'exp', 'floor', 'hypot', 'log', 'log10',
  'mod', 'pow', 'round', 'sin', 'sinh', 'sqrt', 'tan', 'tanh', 'trunc', 'vangle', 'vcross', 'vdot', 'vlinedist', 'vlinesegdist', 'vlineproj',
  'vnormalize', 'vplanedist', 'vplaneproj', 'vscale', 'vscalex', 'vscaley', 'vscalez', 'minvert', 'mrotate', 'mrotatex', 'mrotatey', 'mrotatez',
  'mscale', 'mtranslate', 'create', 'list', 'matrix', 'placement', 'rotation', 'rotationx', 'rotationy', 'rotationz', 'str', 'parsequant',
  'translationm', 'tuple', 'vector', 'address', 'hiddenref', 'href', 'not', 'average', 'count', 'max', 'min', 'stddev', 'sum', 'and', 'or'])

type Tok = { n: number; v?: unknown }
const CONSTANTS: Record<string, { name: 'pi' | 'e' | 'None' | 'True' | 'False'; v: number }> = {
  pi: { name: 'pi', v: Math.PI }, e: { name: 'e', v: Math.E }, None: { name: 'None', v: 0 }, True: { name: 'True', v: 1 }, true: { name: 'True', v: 1 },
  False: { name: 'False', v: 0 }, false: { name: 'False', v: 0 },
}

/** num_change (Expression.l): the digits of a number with `grp` left out and `dez` as the point; a text of 40 characters or more is 0. */
function numChange(text: string, dez: string, grp: string): number {
  let t = '', n = 0
  for (const c of text) {
    if (c === grp) continue
    t += c === dez && dez !== '.' ? '.' : c
    if (++n > 39) return 0
  }
  const v = Number(t)
  if (v === 0 && /[1-9]/.test(t.split(/[eE]/)[0])) throw new PyError('Number underflow.', 'ArithmeticError')
  if (v === Infinity || v === -Infinity) throw new PyError('Number overflow.', 'OverflowError')
  return v
}
/** unquote (Expression.cpp): the text of a <<string>>, escapes resolved. It works on bytes: an escape it does not know drops
 *  one byte, so a backslash before a character of more than one byte leaves the rest of that character behind, and the text
 *  is then not UTF-8 (`bad` says what Python says about it when the string is made). */
function unquote(lexeme: string): { s: string; bad: string | null } {
  const bytes = new TextEncoder().encode(lexeme)
  const out: number[] = []
  let escaped = false
  for (let i = 2; i < bytes.length - 2; i++) {
    const c = bytes[i]
    if (escaped) {
      if (c === 0x74) out.push(9) // t
      else if (c === 0x6e) out.push(10) // n
      else if (c === 0x72) out.push(13) // r
      else if (c === 0x5c || c === 0x27 || c === 0x22) out.push(c)
      escaped = false
    } else if (c === 0x5c) escaped = true
    else out.push(c)
  }
  try {
    return { s: new TextDecoder('utf-8', { fatal: true }).decode(new Uint8Array(out)), bad: null }
  } catch {
    let at = 0
    while (at < out.length) { // the first byte that is not where a character can begin
      const c = out[at]
      const len = c < 0x80 ? 1 : c >= 0xc2 && c < 0xe0 ? 2 : c >= 0xe0 && c < 0xf0 ? 3 : c >= 0xf0 && c < 0xf5 ? 4 : 0
      if (len === 0) break
      if (at + len > out.length) return { s: '', bad: `'utf-8' codec can't decode byte 0x${c.toString(16)} in position ${at}: unexpected end of data` }
      if (out.slice(at + 1, at + len).some((x) => (x & 0xc0) !== 0x80)) return { s: '', bad: `'utf-8' codec can't decode byte 0x${c.toString(16)} in position ${at}: invalid continuation byte` }
      at += len
    }
    return { s: '', bad: `'utf-8' codec can't decode byte 0x${(out[at] ?? 0).toString(16)} in position ${at}: invalid start byte` }
  }
}

class Lexer {
  private i = 0
  constructor(private readonly text: string, private readonly names: ReadonlySet<string>) {}
  private at(re: RegExp): string | null {
    re.lastIndex = this.i
    const m = re.exec(this.text)
    return m ? m[0] : null
  }
  /** The next token, longest match first and the earlier rule on a tie; a character no rule takes is skipped (flex's default rule). */
  next(): Tok {
    for (;;) {
      if (this.i >= this.text.length) return { n: 0 }
      let len = 0, kind = ''
      const consider = (k: string, m: string | null) => { if (m !== null && m.length > len) { len = m.length; kind = k } }
      consider('ws', this.at(RE_WS))
      consider('nl', this.at(RE_NL))
      consider('str', this.at(RE_STRING))
      consider('char', this.at(RE_CHAR))
      for (const op of SIMPLE_OPS) if (this.text.startsWith(op, this.i)) consider('op', op)
      if (this.text[this.i] === '-') consider('minus', '-')
      if (this.text[this.i] === '−') consider('minus', '−')
      consider('unit', this.at(RE_UNIT))
      consider('n1', this.at(RE_N1))
      consider('n2', this.at(RE_N2))
      consider('n3', this.at(RE_N3))
      consider('n4', this.at(RE_N4))
      consider('const', this.at(RE_CONST))
      consider('cell', this.at(RE_CELL1))
      consider('cell', this.at(RE_CELL2))
      consider('cell', this.at(RE_CELL3))
      consider('func', this.at(RE_FUNC))
      consider('id', this.at(RE_IDENT))
      if (len === 0) { // flex's default rule: copy the character to the output and go on
        this.i += String.fromCodePoint(this.text.codePointAt(this.i)!).length
        continue
      }
      const lexeme = this.text.slice(this.i, this.i + len)
      this.i += len
      switch (kind) {
        case 'ws': case 'nl': continue
        case 'str': return { n: T('STRING'), v: unquote(lexeme) }
        case 'char': return { n: T(`'${lexeme}'`), v: lexeme }
        case 'op': return { n: T({ '==': 'EQ', '!=': 'NEQ', '>': 'GT', '<': 'LT', '>=': 'GTE', '<=': 'LTE' }[lexeme]!) }
        case 'minus': return { n: T('MINUSSIGN') }
        case 'unit': {
          if (this.names.has(lexeme)) return { n: T('IDENTIFIER'), v: lexeme }
          const [value, dims] = UNITS[lexeme]
          return { n: T(lexeme === '"' || lexeme === "'" ? 'USUNIT' : 'UNIT'), v: { q: { value, dims }, s: lexeme } }
        }
        case 'n1': case 'n2': case 'n3': {
          const v = kind === 'n2' ? numChange(lexeme, ',', '.') : numChange(lexeme, kind === 'n1' ? '.' : ',', kind === 'n1' ? ',' : '.')
          return { n: T(v === 1 ? 'ONE' : 'NUM'), v }
        }
        case 'n4': {
          const v = BigInt(lexeme)
          if (v >= 9223372036854775807n) throw new PyError('Integer overflow', 'OverflowError')
          return v === 1n ? { n: T('ONE'), v: 1 } : { n: T('INTEGER'), v: Number(v) }
        }
        case 'const': {
          if (this.names.has(lexeme)) return { n: T('IDENTIFIER'), v: lexeme }
          return { n: T('CONSTANT'), v: CONSTANTS[lexeme] }
        }
        case 'cell': return { n: T('CELLADDRESS'), v: lexeme }
        case 'func': {
          const name = lexeme.slice(0, -1).replace(/[ \t\n\v\f\r]+$/, '')
          return { n: T('FUNC'), v: { name, known: FUNCTIONS.has(name) } }
        }
        default: return { n: T('IDENTIFIER'), v: lexeme }
      }
    }
  }
}

// ─── The expression classes' checks and printing ─────────────────────────────────────────────────

/** What each function wants of its argument count, in the words FunctionExpression's constructor uses (null: any count, but one). */
const ARITY: Record<string, [(n: number) => boolean, string] | null> = (() => {
  const one: [(n: number) => boolean, string] = [(n) => n === 1, 'exactly one required.']
  const two: [(n: number) => boolean, string] = [(n) => n === 2, 'exactly two required.']
  const twoThree: [(n: number) => boolean, string] = [(n) => n >= 2 && n <= 3, 'exactly two, or three required.']
  const three: [(n: number) => boolean, string] = [(n) => n === 3, 'exactly three required.']
  const atLeastOne: [(n: number) => boolean, string] = [(n) => n >= 1, 'at least one required.']
  const out: Record<string, [(n: number) => boolean, string] | null> = {}
  for (const f of ['abs', 'acos', 'asin', 'atan', 'cbrt', 'ceil', 'cos', 'cosh', 'exp', 'floor', 'hiddenref', 'href', 'log', 'log10', 'minvert', 'rotationx',
    'rotationy', 'rotationz', 'round', 'sin', 'sinh', 'sqrt', 'str', 'parsequant', 'tan', 'tanh', 'trunc', 'vnormalize', 'not']) out[f] = one
  out.placement = [(n) => n <= 3, 'exactly one, two, or three required.']
  out.translationm = [(n) => n === 1 || n === 3, 'exactly one or three required.']
  for (const f of ['atan2', 'mod', 'mrotatex', 'mrotatey', 'mrotatez', 'pow', 'vangle', 'vcross', 'vdot', 'vscalex', 'vscaley', 'vscalez']) out[f] = two
  for (const f of ['address', 'cath', 'hypot', 'rotation']) out[f] = twoThree
  for (const f of ['mtranslate', 'mscale']) out[f] = [(n) => n === 2 || n === 4, 'exactly two or four required.']
  out.mrotate = [(n) => n >= 2 && n <= 4, 'exactly two, three, or four required.']
  for (const f of ['vector', 'vlinedist', 'vlinesegdist', 'vlineproj', 'vplanedist', 'vplaneproj']) out[f] = three
  out.vscale = [(n) => n === 4, 'exactly four required.']
  out.matrix = [(n) => n <= 16, 'exactly 16 or less required.']
  for (const f of ['average', 'count', 'create', 'max', 'min', 'stddev', 'sum', 'and', 'or']) out[f] = atLeastOne
  out.list = null
  out.tuple = null
  return out
})()

/** Expression::priority(): the operators' (OperatorExpression::priority), a conditional's, and 20 for the rest. */
function priority(n: Node): number {
  switch (n.k) {
    case 'op':
      switch (n.op) {
        case '==': case '!=': case '<': case '>': case '<=': case '>=': return 1
        case '+': case '-': return 3
        case '*': case '/': case '%': return 4
        case '^': return 5
        default: return 6
      }
    case 'neg': case 'pos': return 6
    case 'cond': return 2
    default: return 20
  }
}
const isRightAssociative = (op: BinOpName) => op === '+' || op === '*'
const isCommutative = (op: BinOpName) => op === '==' || op === '!=' || op === '+' || op === '*'

/** The text of a number as Expression.cpp prints it: setprecision(15), the default float format. */
const numberText = (v: number) => toNumber(v, 'Default', 15)
/** App::quote: <<text>> with the characters the lexer reads as escapes written as escapes. */
function quote(s: string): string {
  let out = '<<'
  for (const c of s) {
    if (c === '\n') out += '\\n'
    else if (c === '\t') out += '\\t'
    else if (c === '\r') out += '\\r'
    else if (c === '\\') out += '\\\\'
    else if (c === '"') out += '\\"'
    else if (c === "'") out += "\\'"
    else out += c
  }
  return out + '>>'
}
/** ObjectIdentifier::toString: the property, a '.' before it if it is the owner's own and attributes follow. */
function pathText(p: VarPath): string {
  const props = p.names.map((n, i) => (i === 0 ? n : '.' + n)).join('')
  return (p.local || p.names.length > 1 ? '.' : '') + props + p.sub.map((c) => idCompText(c)).join('')
}
function idCompText(c: IdComp): string {
  switch (c.k) {
    case 'attr': return '.' + c.name
    case 'array': return `[${c.i}]`
    case 'map': return `[${quote(c.key)}]`
    case 'range': return `[${c.b}:${c.e === null ? '' : c.e}${c.s !== 1 ? ':' + c.s : ''}]`
  }
}
/** Expression::toString. */
export function toText(n: Node): string {
  switch (n.k) {
    case 'num': return numberText(n.v)
    case 'const': return n.name
    case 'unit': return n.s
    case 'str': return quote(n.s)
    case 'range': return `${n.a}:${n.b}`
    case 'var': {
      let s = pathText(n.path)
      for (const c of n.comps) {
        if ('name' in c) s += '.' + c.name
        else s += `[${c.e1 ? toText(c.e1) : ''}${c.e2 || c.range ? ':' : ''}${c.e2 ? toText(c.e2) : ''}${c.e3 ? ':' + toText(c.e3) : ''}]`
      }
      return s
    }
    case 'neg': case 'pos': {
      const parens = priority(n.a) < 6
      return (n.k === 'neg' ? '-' : '+') + (parens ? '(' : '') + toText(n.a) + (parens ? ')' : '')
    }
    case 'op': {
      let left = false
      const lop = n.l.k === 'op' ? n.l.op : null
      if (priority(n.l) < priority(n)) left = true // the same operator on the left needs none: associativity is always to the left
      if (n.op === 'unit' && n.l.k !== 'num' && n.l.k !== 'const') left = true
      let s = left ? `(${toText(n.l)})` : toText(n.l)
      s += n.op === 'unit' ? ' ' : ` ${n.op} `
      let right = false
      const rop = n.r.k === 'op' ? n.r.op : null
      if (priority(n.r) < priority(n)) right = true
      else if (rop === n.op) {
        if (!isRightAssociative(n.op)) right = true
        else if (!isCommutative(n.op)) right = true
      } else if (priority(n.r) === priority(n)) {
        if (!isRightAssociative(n.op) || rop === '%') right = true
      }
      s += right ? `(${toText(n.r)})` : toText(n.r)
      return s
    }
    case 'fn': return `${n.name}(${n.args.map(toText).join('; ')})`
    case 'cond': {
      const wrap = (x: Node) => (priority(x) <= 2 ? `(${toText(x)})` : toText(x))
      return `${toText(n.c)} ? ${wrap(n.t)} : ${wrap(n.f)}`
    }
  }
}
/** The suffix FreeCAD appends to an error: "\nin expression: ...". */
const inExpr = (msg: string, n: Node) => `${msg}\nin expression: ${toText(n)}`

// ─── The parser (Expression.y's actions on the tables) ───────────────────────────────────────────────────────

type Comp = ExprComp
const essentiallyEqual = (a: number, b: number) => Math.abs(a - b) <= Math.min(Math.abs(a), Math.abs(b)) * Number.EPSILON
const numLike = (n: Node | null): n is Extract<Node, { k: 'num' | 'const' }> => !!n && (n.k === 'num' || n.k === 'const')
const essentiallyInteger = (v: number): number | null => (Number.isFinite(v) && Number.isInteger(v) && Math.abs(v) <= 9223372036854775807 ? v : null)

/** VariableExpression::addComponent: a constant index or range is folded into the identifier, the rest stays an expression. */
function addComponent(n: Extract<Node, { k: 'var' }>, c: Comp): void {
  if (n.comps.length === 0) {
    if ('name' in c) { n.path.sub.push({ k: 'attr', name: c.name }); return }
    folding: do {
      if (!c.e1 && !c.e2) { n.path.sub.push({ k: 'range', b: 0, e: null, s: 1 }); return } // a range with no bounds: Bison's `createComponent(0,0,e)` drops the step too
      let l1 = 0, l2 = 0
      if (c.e3) {
        if (!numLike(c.e3) || !essentiallyEqual(c.e3.v, 1)) break folding
      }
      if (c.e1) {
        if (!numLike(c.e1)) {
          if (c.e2 || c.e3) break folding
          if (c.e1.k !== 'str') break folding
          n.path.sub.push({ k: 'map', key: c.e1.s })
          return
        }
        const i1 = essentiallyInteger(c.e1.v)
        if (i1 === null) break folding
        l1 = i1
        if (!c.range) { n.path.sub.push({ k: 'array', i: l1 }); return }
        if (!c.e2) { n.path.sub.push({ k: 'range', b: l1, e: l2, s: 1 }); return }
      }
      if (numLike(c.e2)) {
        const i2 = essentiallyInteger(c.e2.v)
        if (i2 !== null) { n.path.sub.push({ k: 'range', b: l1, e: i2, s: 1 }); return }
      }
    } while (false)
  }
  n.comps.push(c)
}

const op = (o: BinOpName, l: Node, r: Node): Node => ({ k: 'op', op: o, l, r })
const emptyPath = (): VarPath => ({ doc: null, obj: null, local: false, names: [], sub: [] })
const mkVar = (path: VarPath): Extract<Node, { k: 'var' }> => ({ k: 'var', path, comps: [] })

type Ctx = { result: Node | null; value: boolean; unit: boolean; owner?: string }
type V = any // eslint-disable-line @typescript-eslint/no-explicit-any

/** FunctionExpression's constructor: the checks on the name and the number of arguments. */
function makeFunction(tok: { name: string; known: boolean }, args: Node[]): Node {
  if (!tok.known) throw new PyError('Unknown function', 'ParserError', 'syntax')
  const node: Node = { k: 'fn', f: tok.name, name: tok.name, args }
  const rule = ARITY[tok.name]
  if (rule && !rule[0](args.length)) throw new PyError(inExpr(`Invalid number of arguments: ${rule[1]}`, node), 'ExpressionError')
  return node
}

/** The semantic actions, by the text of the rule they belong to (expr-grammar.ts has it with each rule). */
const ACTIONS: Record<string, (v: V[], ctx: Ctx) => V> = {
  'input: exp': (v, c) => { c.result = v[0]; c.value = true },
  'input: unit_exp': (v, c) => { c.result = v[0]; c.unit = true },
  'unit_num: num unit_exp %prec NUM_AND_UNIT': (v) => op('unit', v[0], v[1]),
  "unit_num: '(' exp ')' unit_exp %prec NUM_AND_UNIT": (v) => op('unit', v[1], v[3]),
  'unit_num: num us_building_unit num us_building_unit %prec NUM_AND_UNIT': (v) => op('+', op('unit', v[0], v[1]), op('unit', v[2], v[3])),
  'exp: num': (v) => v[0],
  'exp: unit_num': (v) => v[0],
  'exp: STRING': (v) => ({ k: 'str', s: v[0].s, ...(v[0].bad ? { bad: v[0].bad } : {}) }),
  'exp: identifier': (v) => mkVar(v[0]),
  'exp: MINUSSIGN exp %prec NEG': (v) => ({ k: 'neg', a: v[1] }),
  "exp: '+' exp %prec POS": (v) => ({ k: 'pos', a: v[1] }),
  "exp: exp '+' exp": (v) => op('+', v[0], v[2]),
  'exp: exp MINUSSIGN exp': (v) => op('-', v[0], v[2]),
  "exp: exp '*' exp": (v) => op('*', v[0], v[2]),
  "exp: exp '/' exp": (v) => op('/', v[0], v[2]),
  "exp: exp '%' exp": (v) => op('%', v[0], v[2]),
  "exp: exp '/' unit_exp": (v) => op('/', v[0], v[2]),
  "exp: exp '^' exp": (v) => op('^', v[0], v[2]),
  'exp: exp EQ exp': (v) => op('==', v[0], v[2]),
  'exp: exp NEQ exp': (v) => op('!=', v[0], v[2]),
  'exp: exp LT exp': (v) => op('<', v[0], v[2]),
  'exp: exp GT exp': (v) => op('>', v[0], v[2]),
  'exp: exp GTE exp': (v) => op('>=', v[0], v[2]),
  'exp: exp LTE exp': (v) => op('<=', v[0], v[2]),
  'exp: indexable': (v) => v[0],
  "exp: FUNC args ')'": (v) => makeFunction(v[0], v[1]),
  "exp: exp '?' exp ':' exp": (v) => ({ k: 'cond', c: v[0], t: v[2], f: v[4] }),
  "exp: '(' exp ')'": (v) => v[1],
  'num: ONE': (v) => ({ k: 'num', v: v[0] }),
  'num: NUM': (v) => ({ k: 'num', v: v[0] }),
  'num: INTEGER': (v) => ({ k: 'num', v: v[0] }),
  'num: CONSTANT': (v) => ({ k: 'const', name: v[0].name, v: v[0].v }),
  'args: exp': (v) => [v[0]],
  'args: range': (v) => [v[0]],
  "args: args ',' exp": (v) => [...v[0], v[2]],
  "args: args ';' exp": (v) => [...v[0], v[2]],
  "args: args ',' range": (v) => [...v[0], v[2]],
  "args: args ';' range": (v) => [...v[0], v[2]],
  "range: id_or_cell ':' id_or_cell": (v) => ({ k: 'range', a: v[0], b: v[2] }),
  'us_building_unit: USUNIT': (v) => ({ k: 'unit', q: v[0].q, s: v[0].s }),
  'other_unit: UNIT': (v) => ({ k: 'unit', q: v[0].q, s: v[0].s }),
  'unit_exp: other_unit': (v) => v[0],
  'unit_exp: us_building_unit': (v) => v[0],
  "unit_exp: unit_exp '/' unit_exp": (v) => op('/', v[0], v[2]),
  "unit_exp: unit_exp '*' unit_exp": (v) => op('*', v[0], v[2]),
  "unit_exp: unit_exp '^' integer": (v) => op('^', v[0], { k: 'num', v: v[2] }),
  "unit_exp: unit_exp '^' MINUSSIGN integer": (v) => op('^', v[0], { k: 'neg', a: { k: 'num', v: v[3] } }),
  "unit_exp: '(' unit_exp ')'": (v) => v[1],
  'integer: INTEGER': (v) => v[0],
  'integer: ONE': (v) => v[0],
  'id_or_cell: IDENTIFIER': (v) => v[0],
  'id_or_cell: CELLADDRESS': (v) => v[0],
  'identifier: id_or_cell': (v) => ({ ...emptyPath(), names: [v[0]] }),
  'identifier: iden': (v) => v[0],
  "iden: '.' STRING '.' id_or_cell": (v) => ({ ...emptyPath(), local: true, names: [v[3]] }),
  "iden: '.' id_or_cell": (v) => ({ ...emptyPath(), local: true, names: [v[1]] }),
  "iden: object '.' STRING '.' id_or_cell": (v) => ({ ...emptyPath(), obj: v[0], names: [v[4]] }),
  // ObjectIdentifier::resolveAmbiguity: the first name is the owner (dropped) or else a property of the owner, then an attribute
  "iden: object '.' id_or_cell": (v, c) => ({ ...emptyPath(), names: v[0].name === c.owner ? [v[2]] : [v[0].name, v[2]] }),
  "iden: document '#' object '.' id_or_cell": (v) => ({ ...emptyPath(), doc: v[0], obj: v[2], names: [v[4]] }),
  "iden: document '#' object '.' STRING '.' id_or_cell": (v) => ({ ...emptyPath(), doc: v[0], obj: v[2], names: [v[6]] }),
  "iden: iden '.' IDENTIFIER": (v) => ({ ...v[0], names: [...v[0].names, v[2]] }),
  "indexer: '[' exp ']'": (v) => ({ e1: v[1], e2: null, e3: null, range: false }),
  "indexer: '[' exp ':' ']'": (v) => ({ e1: v[1], e2: null, e3: null, range: true }),
  "indexer: '[' ':' exp ']'": (v) => ({ e1: null, e2: v[2], e3: null, range: true }),
  "indexer: '[' ':' ':' exp ']'": (v) => ({ e1: null, e2: null, e3: v[3], range: true }),
  "indexer: '[' exp ':' exp ']'": (v) => ({ e1: v[1], e2: v[3], e3: null, range: true }),
  "indexer: '[' exp ':' ':' exp ']'": (v) => ({ e1: v[1], e2: null, e3: v[4], range: true }),
  "indexer: '[' ':' exp ':' exp ']'": (v) => ({ e1: null, e2: v[2], e3: v[4], range: true }),
  "indexer: '[' exp ':' exp ':' exp ']'": (v) => ({ e1: v[1], e2: v[3], e3: v[5], range: true }),
  'indexable: identifier indexer': (v) => { const n = mkVar(v[0]); addComponent(n, v[1]); return n },
  'indexable: indexable indexer': (v) => { addComponent(v[0], v[1]); return v[0] },
  "indexable: indexable '.' IDENTIFIER": (v) => { addComponent(v[0], { name: v[2] }); return v[0] },
  'document: STRING': (v) => ({ name: v[0].s, str: true }),
  'document: IDENTIFIER': (v) => ({ name: v[0], str: false }),
  'object: STRING': (v) => ({ name: v[0].s, str: true }),
  'object: id_or_cell': (v) => ({ name: v[0], str: false }),
}
const RULE_ACTIONS = RULES.map(([, , text]) => {
  const a = ACTIONS[text]
  if (!a && text !== '$accept: input $end') throw new Error(`expr.ts has no action for the grammar rule "${text}": regenerate expr-grammar.ts and update ACTIONS`)
  return a
})

/** Parse an expression (without a leading "="), as Expression.y does, building FreeCAD's expression classes. `names` are
 *  the parameters it may use: a unit's or constant's name among them reads as the parameter. Throws what FreeCAD throws:
 *  ParserError for text that is not an expression ("Failed to parse expression '...'"), and the lexer's and
 *  constructors' own errors. `owner` is the name of the object the expression belongs to. */
export function parseExpr(text: string, names: ReadonlySet<string> = new Set(), owner?: string): Node {
  const lexer = new Lexer(text, names)
  const ctx: Ctx = { result: null, value: false, unit: false, owner }
  const states = [0]
  const values: V[] = [undefined]
  let tok: Tok | null = null
  for (;;) {
    const s = states[states.length - 1]
    const [shifts, reds, def, gotos, needsToken] = STATES[s]
    let action: { shift: number } | { reduce: number } | null = null
    if (needsToken) {
      tok ??= lexer.next()
      for (let i = 0; i < shifts.length; i += 2) if (shifts[i] === tok.n) { action = { shift: shifts[i + 1] }; break }
      if (!action) for (let i = 0; i < reds.length; i += 2) if (reds[i] === tok.n) { action = { reduce: reds[i + 1] }; break }
    }
    if (!action) {
      if (def < 0) throw parseError(text)
      action = { reduce: def }
    }
    if ('shift' in action) {
      if (action.shift < 0) break // $end shifted: the input is complete
      states.push(action.shift)
      values.push(tok!.v)
      tok = null
      continue
    }
    const [lhs, len] = RULES[action.reduce]
    const args = values.splice(values.length - len, len)
    states.length -= len
    const out = RULE_ACTIONS[action.reduce](args, ctx)
    values.push(out)
    const g = STATES[states[states.length - 1]][3]
    let next = -1
    for (let i = 0; i < g.length; i += 2) if (g[i] === lhs) { next = g[i + 1]; break }
    if (next < 0) throw parseError(text)
    states.push(next)
  }
  if (!ctx.result) throw new PyError(`Unknown error in expression '${text}'`, 'ParserError', 'syntax')
  if (!ctx.value) throw new PyError('Expression can not evaluate to a value.', 'FreeCADError', 'syntax')
  return ctx.result
}

// ─── Evaluation (Expression.cpp's _getPyValue) ────────────────────────────────────────────────────

/** What an expression can name: the owner's properties, as Python values (a Quantity is a Length or the like; a plain number
 *  here is a Float, as PropertyFloat gives). */
export type Env = {
  vars: Record<string, PyVal | Quantity>
  /** the object that owns the expression (its name) and its document; a name that is neither is not found. */
  owner?: string
  doc?: string
}
const isPyVal = (x: PyVal | Quantity): x is PyVal => 't' in x
function propertyValue(x: PyVal | Quantity): PyVal {
  if (isPyVal(x)) return x
  return P.isDimless(x.dims) ? P.float(x.value) : { t: 'qty', q: x }
}

const rt = (message: string) => new PyError(message, 'RuntimeError')
const refText = (r: Ref) => (r.str ? `<<${r.name}>>` : r.name)

function resolveProperty(n: Extract<Node, { k: 'var' }>, env: Env): { value: PyVal; rest: string[] } {
  const owner = env.owner ?? '', doc = env.doc ?? ''
  const p = n.path
  if (p.doc && p.doc.name !== doc) throw rt(`Document '${refText(p.doc)}' not found in '${p.doc.name}'`)
  if (p.obj && p.obj.name !== owner) throw rt(`Document object '${refText(p.obj)}' not found in '${doc}'`)
  const prop = p.names[0]
  if (!Object.prototype.hasOwnProperty.call(env.vars, prop)) throw rt(`Property '${prop}' not found in '${owner}'`)
  return { value: propertyValue(env.vars[prop]), rest: p.names.slice(1) }
}
/** ObjectIdentifier::Component::get: an attribute, index, key or slice the parser folded into the name. */
function applyIdComp(c: IdComp, v: PyVal): PyVal {
  switch (c.k) {
    case 'attr': return P.getAttr(v, c.name)
    case 'array': return P.getItem(v, P.int(c.i))
    case 'map': return mapItem(v, c.key)
    case 'range': return P.getSlice(v, P.int(c.b), c.e === null ? null : P.int(c.e), c.s === 1 ? null : P.int(c.s))
  }
}
/** Py::Mapping(obj).getItem(key) with a string key. */
function mapItem(v: PyVal, key: string): PyVal {
  if (v.t === 'str') throw new PyError("string indices must be integers, not 'str'", 'TypeError')
  if (v.t === 'list' || v.t === 'tuple') throw new PyError(`${v.t} indices must be integers or slices, not str`, 'TypeError')
  throw new PyError(`PyCXX: Error creating object of type N2Py7MapBaseINS_6ObjectEEE from ${P.repr(v)}`, 'TypeError')
}
function evalVar(n: Extract<Node, { k: 'var' }>, env: Env): PyVal {
  const { value, rest } = resolveProperty(n, env)
  let v = value
  for (const name of rest) v = P.getAttr(v, name)
  for (const c of n.path.sub) v = applyIdComp(c, v)
  for (const c of n.comps) v = applyExprComp(n, c, v, env)
  return v
}
/** Expression::Component::get: an index or a slice by expressions, with the owner's text on an error. */
function applyExprComp(owner: Node, c: Comp, v: PyVal, env: Env): PyVal {
  if ('name' in c) return P.getAttr(v, c.name)
  const wrap = <T>(f: () => T): T => {
    try { return f() } catch (e) {
      if (e instanceof PyError && !e.message.includes('\nin expression: ')) throw new PyError(inExpr(e.message, owner), e.etype, e.kind)
      throw e
    }
  }
  if (!c.range && !c.e2 && !c.e3) {
    const index = ev(c.e1!, env)
    return wrap(() => {
      if (v.t === 'str' || v.t === 'list' || v.t === 'tuple') return P.getItem(v, index)
      if (index.t !== 'int' && index.t !== 'bool') throw new PyError(`'${P.typeName(index)}' object cannot be interpreted as an integer`, 'TypeError')
      return P.getItem(v, index)
    })
  }
  const a = c.e1 ? ev(c.e1, env) : null, b = c.e2 ? ev(c.e2, env) : null, s = c.e3 ? ev(c.e3, env) : null
  return wrap(() => {
    if (v.t !== 'str' && v.t !== 'list' && v.t !== 'tuple') throw new PyError(`'${P.typeName(v)}' object is not subscriptable`, 'TypeError')
    return P.getSlice(v, a, b, s)
  })
}

function withExpr<T>(n: Node, f: () => T): T {
  try { return f() } catch (e) {
    if (e instanceof PyError && !e.raw && !e.message.includes('\nin expression: ')) throw new PyError(inExpr(e.message, n), e.etype, e.kind)
    throw e
  }
}

const OPERATOR_TO_BIN: Partial<Record<BinOpName, P.BinOp>> = { '+': 'add', '-': 'sub', '*': 'mul', '/': 'div', '%': 'mod', '^': 'pow', unit: 'mul' }
const OPERATOR_TO_CMP: Partial<Record<BinOpName, P.CmpOp>> = { '==': 'eq', '!=': 'ne', '<': 'lt', '<=': 'le', '>': 'gt', '>=': 'ge' }
const supportedOperand = (a: PyVal) => P.isNumeric(a) || a.t === 'str' || a.t === 'list' || a.t === 'obj'

/** OperatorExpression's calc(): for security only numbers, strings and lists are accepted, and then Python's operators run. */
function calc(n: Node, o: BinOpName | 'neg' | 'pos', left: Node, right: Node | null, env: Env): PyVal {
  const l = ev(left, env)
  if (!supportedOperand(l)) throw new PyError(inExpr('Unsupported operator', n), 'TypeError')
  if (o === 'pos') return withExpr(n, () => P.pos(l))
  if (o === 'neg') return withExpr(n, () => P.neg(l))
  const r = ev(right!, env)
  if ((o !== '%' || l.t !== 'str') && !supportedOperand(r)) throw new PyError(inExpr('Unsupported operator', n), 'TypeError')
  const cmp = OPERATOR_TO_CMP[o as BinOpName]
  if (cmp) return withExpr(n, () => P.bool(P.compare(l, r, cmp)))
  const bin = OPERATOR_TO_BIN[o as BinOpName]!
  return withExpr(n, () => P.binary(bin, l, r))
}

/** Evaluate a tree against the owner's properties; FreeCAD's getPyValue(). */
export function ev(n: Node, env: Env): PyVal {
  switch (n.k) {
    case 'num': return P.fromQuantity({ value: n.v, dims: ZERO })
    case 'const':
      if (n.name === 'None') return P.none
      if (n.name === 'True') return P.bool(true)
      if (n.name === 'False') return P.bool(false)
      return P.fromQuantity({ value: n.v, dims: ZERO })
    case 'unit': return P.fromQuantity(n.q)
    case 'str':
      if (n.bad) throw new PyError(n.bad, 'UnicodeDecodeError', 'eval', true)
      return P.str(n.s)
    case 'var': return evalVar(n, env)
    case 'neg': return calc(n, 'neg', n.a, null, env)
    case 'pos': return calc(n, 'pos', n.a, null, env)
    case 'op': return calc(n, n.op, n.l, n.r, env)
    case 'cond': return P.truth(ev(n.c, env)) ? ev(n.t, env) : ev(n.f, env)
    case 'range': return rangeList(n, env)
    case 'fn': return evalFunction(n, env)
  }
}

// ─── Cell ranges (RangeExpression) ─────────────────────────────────────────────────────────────

const CELL = /^(\$?)([A-Z]{1,2})(\$?)([0-9]+)$/
function stringToAddress(s: string): { row: number; col: number } | null {
  const m = CELL.exec(s)
  if (!m) return null
  let col = 0
  for (const ch of m[2]) col = col * 26 + (ch.charCodeAt(0) - 64)
  const row = Number(m[4])
  return row >= 1 && row <= 16384 && col >= 1 && col <= 702 ? { row, col } : null
}
const columnName = (col: number) => (col > 26 ? String.fromCharCode(64 + Math.floor((col - 1) / 26)) : '') + String.fromCharCode(65 + ((col - 1) % 26))
function rangeCells(n: Extract<Node, { k: 'range' }>): string[] {
  const c1 = stringToAddress(n.a), c2 = stringToAddress(n.b)
  if (!c1 || !c2) throw new PyError(inExpr(`Invalid cell range ${n.a}:${n.b}`, n), 'ExpressionError')
  const out: string[] = []
  for (let r = Math.min(c1.row, c2.row); r <= Math.max(c1.row, c2.row); r++)
    for (let c = Math.min(c1.col, c2.col); c <= Math.max(c1.col, c2.col); c++) out.push(`${columnName(c)}${r}`)
  return out
}
function rangeList(n: Extract<Node, { k: 'range' }>, env: Env): PyVal {
  const items: PyVal[] = []
  for (const addr of rangeCells(n)) if (Object.prototype.hasOwnProperty.call(env.vars, addr)) items.push(propertyValue(env.vars[addr]))
  return { t: 'list', v: items }
}

// ─── Functions (FunctionExpression::evaluate) ──────────────────────────────────────────────────────

const AGGREGATES = new Set(['sum', 'average', 'stddev', 'count', 'min', 'max', 'and', 'or'])
const asBool = (v: number) => Math.abs(v) >= 1e-7
const qty0: Quantity = { value: 0, dims: ZERO }

/** The collectors of the aggregate functions (Collector and its subclasses in Expression.cpp), fed one value at a time. */
class Collector {
  private q: Quantity = qty0
  private first = true
  private n = 0
  private mean: Quantity = qty0
  private m2: Quantity = qty0
  constructor(private readonly f: string) {}
  collect(v: Quantity): void {
    const f = this.f
    if (f !== 'and' && f !== 'or' && this.first) this.q = { value: this.q.value, dims: v.dims }
    switch (f) {
      case 'sum': this.q = P.qAddAssign(this.q, v); break
      case 'average': this.q = P.qAddAssign(this.q, v); this.n++; break
      case 'count': this.n++; break
      case 'min': if (this.first || P.qLess(v, this.q)) this.q = v; break
      case 'max': if (this.first || P.qGreater(v, this.q)) this.q = v; break
      case 'and':
        if (this.first) this.q = { value: asBool(v.value) ? 1 : 0, dims: ZERO }
        else if (!asBool(v.value)) this.q = { value: 0, dims: ZERO }
        break
      case 'or':
        if (this.first) this.q = { value: asBool(v.value) ? 1 : 0, dims: ZERO }
        else if (asBool(v.value)) this.q = { value: 1, dims: ZERO }
        break
      case 'stddev': {
        if (this.first) { this.m2 = { value: 0, dims: P.unitMul(v.dims, v.dims) }; this.mean = { value: 0, dims: v.dims }; this.n = 0 }
        const delta = P.qSub(v, this.mean)
        this.n++
        this.mean = P.qAdd(this.mean, P.qDiv(delta, { value: this.n, dims: ZERO }))
        this.m2 = P.qAdd(this.m2, P.qMul(delta, P.qSub(v, this.mean)))
        break
      }
    }
    this.first = false
  }
  result(): Quantity {
    switch (this.f) {
      case 'average': return P.qDiv(this.q, { value: this.n, dims: ZERO })
      case 'count': return { value: this.n, dims: ZERO }
      case 'stddev':
        if (this.n < 2) throw new PyError('Invalid number of entries: at least two required.', 'ExpressionError')
        return { value: P.qPowQ(P.qDiv(this.m2, { value: this.n - 1, dims: ZERO }), { value: 0.5, dims: ZERO }).value, dims: this.mean.dims }
      default: return this.q
    }
  }
}

/** boost::math::round and trunc (boost/math/special_functions/round.hpp, trunc.hpp): neither takes a value that is not finite. */
function boostRound(v: number, name: 'round' | 'trunc'): number {
  if (!Number.isFinite(v)) throw new PyError(`Error in function boost::math::${name}<double>(double): Value ${Number.isNaN(v) ? 'nan' : v > 0 ? 'inf' : '-inf'} can not be represented in the target integer type.`, 'FreeCADError')
  if (name === 'trunc') return v >= 0 ? Math.floor(v) : Math.ceil(v)
  if (-0.5 < v && v < 0.5) return 0
  if (v > 0) { const c = Math.ceil(v); return c - v > 0.5 ? c - 1 : c }
  const fl = Math.floor(v)
  return v - fl > 0.5 ? fl + 1 : fl
}

const pi = Math.PI
const toRadians = (d: number) => d * (pi / 180)

function evalFunction(n: Extract<Node, { k: 'fn' }>, env: Env): PyVal {
  const f = n.f, args = n.args
  const fail = (cls: string, msg: string): never => { throw new PyError(inExpr(msg, n), cls) }
  if (AGGREGATES.has(f)) {
    const c = new Collector(f)
    for (const a of args) {
      if (a.k === 'range') {
        for (const addr of rangeCells(a)) {
          if (!Object.prototype.hasOwnProperty.call(env.vars, addr)) continue
          const q = P.toQuantity(propertyValue(env.vars[addr]))
          if (!q) throw new PyError(inExpr('Invalid property type for aggregate.', n), 'ExpressionError')
          c.collect(q)
        }
      } else {
        const q = P.toQuantity(ev(a, env))
        if (q) c.collect(q)
      }
    }
    return P.fromQuantity(c.result())
  }
  if (f === 'list' || f === 'tuple') {
    if (args.length === 1 && args[0].k === 'range') {
      const l = ev(args[0], env)
      if (f === 'list') return l
      return fail('TypeError', `PyCXX: Error creating object of type N2Py5TupleE from ${P.repr(l)}`)
    }
    const items = args.map((a) => ev(a, env))
    return { t: f, v: items }
  }
  if (args.length === 0) fail('ExpressionError', 'Function requires at least one argument.')
  switch (f) {
    case 'str': return P.str(P.pyStr(ev(args[0], env)))
    case 'parsequant': {
      const text = P.pyStr(ev(args[0], env))
      try {
        const q = parseQuantity(text)
        return { t: 'qty', q }
      } catch (e) {
        if (e instanceof PyError) throw e
        if (e instanceof QuantityError) throw new PyError(e.message, e.kind === 'mismatch' ? 'ArithmeticError' : e.kind === 'syntax' ? 'ParserError' : 'ArithmeticError', e.kind)
        throw e
      }
    }
    case 'hiddenref': case 'href': return ev(args[0], env)
    case 'address': {
      const row = ev(args[0], env), col = ev(args[1], env)
      if (row.t !== 'int' && row.t !== 'bool') return fail('ExpressionError', 'Function requires the first argument to be an integer.')
      if (col.t !== 'int' && col.t !== 'bool') return fail('ExpressionError', 'Function requires the second argument to be an integer.')
      let absRow = true, absCol = true
      if (args.length > 2) {
        const ref = ev(args[2], env)
        if (ref.t !== 'int' && ref.t !== 'bool') return fail('ExpressionError', 'Function requires the third argument to be an integer.')
        const value = Number(ref.t === 'int' ? ref.v : ref.v ? 1n : 0n)
        if (value < 1 || value > 4) return fail('ExpressionError', 'Invalid reference type: must be 1, 2, 3, or 4.')
        absRow = value === 1 || value === 2
        absCol = value === 1 || value === 3
      }
      const r = Number(row.t === 'int' ? row.v : row.v ? 1n : 0n), c = Number(col.t === 'int' ? col.v : col.v ? 1n : 0n)
      if (r < 1 || r > 16384 || c < 1 || c > 702) return fail('ExpressionError', 'Cell address out of bounds.')
      return P.str(`${absCol ? '$' : ''}${columnName(c)}${absRow ? '$' : ''}${r}`)
    }
    case 'create': case 'matrix': case 'placement': case 'rotation': case 'vector': case 'translationm': case 'minvert': case 'mrotate': case 'mrotatex':
    case 'mrotatey': case 'mrotatez': case 'mscale': case 'mtranslate': case 'rotationx': case 'rotationy': case 'rotationz':
    case 'vangle': case 'vcross': case 'vdot': case 'vlinedist': case 'vlinesegdist': case 'vlineproj': case 'vnormalize': case 'vplanedist':
    case 'vplaneproj': case 'vscale': case 'vscalex': case 'vscaley': case 'vscalez':
      return evalObjectFunction(n, env)
  }
  // The numeric functions: every argument is made a quantity first, in order.
  const arg = (i: number, msg: string): Quantity => {
    const q = P.toQuantity(ev(args[i], env))
    if (!q) return fail('TypeError', msg)
    return q
  }
  const v1 = arg(0, 'Invalid first argument.')
  const v2 = args.length > 1 ? arg(1, 'Invalid second argument.') : null
  const v3 = args.length > 2 ? arg(2, 'Invalid third argument.') : null
  let value = v1.value
  let dims: Dims = ZERO
  let scaler = 1
  const angleOrNone = (q: Quantity) => P.isDimless(q.dims) || P.sameDims(q.dims, P.ANGLE)
  switch (f) {
    case 'cos': case 'sin': case 'tan':
      if (!angleOrNone(v1)) return fail('ExpressionError', 'Unit must be either empty or an angle.')
      value = toRadians(value)
      break
    case 'acos': case 'asin': case 'atan':
      if (!P.isDimless(v1.dims)) return fail('ExpressionError', 'Unit must be empty.')
      dims = P.ANGLE
      scaler = 180 / pi
      break
    case 'exp': case 'log': case 'log10': case 'sinh': case 'tanh': case 'cosh':
      if (!P.isDimless(v1.dims)) return fail('ExpressionError', 'Unit must be empty.')
      break
    case 'round': case 'trunc': case 'ceil': case 'floor': case 'abs': dims = v1.dims; break
    case 'sqrt': dims = P.unitRoot(v1.dims, 2); break
    case 'cbrt': dims = P.unitRoot(v1.dims, 3); break
    case 'atan2':
      if (!P.sameDims(v1.dims, v2!.dims)) return fail('ExpressionError', 'Units must be equal.')
      dims = P.ANGLE
      scaler = 180 / pi
      break
    case 'mod':
      if (!P.sameDims(v1.dims, v2!.dims) && !P.isDimless(v1.dims) && !P.isDimless(v2!.dims)) return fail('ExpressionError', 'Units must be equal or dimensionless.')
      dims = v1.dims
      break
    case 'pow': {
      if (!P.isDimless(v2!.dims)) return fail('ExpressionError', 'Exponent is not allowed to have a unit.')
      const exponent = v2!.value
      if (!P.isDimless(v1.dims)) {
        if (exponent - boostRound(exponent, 'round') < 1e-9) dims = P.unitPow(v1.dims, exponent)
        else return fail('ExpressionError', 'Exponent must be an integer when used with a unit.')
      }
      break
    }
    case 'hypot': case 'cath':
      if (!P.sameDims(v1.dims, v2!.dims)) return fail('ExpressionError', 'Units must be equal.')
      if (args.length > 2 && !P.sameDims(v2!.dims, v3!.dims)) return fail('ExpressionError', 'Units must be equal.')
      dims = v1.dims
      break
    case 'not': break
    default: return fail('ExpressionError', `Unknown function: ${f}`)
  }
  let output: number
  switch (f) {
    case 'acos': output = Math.acos(value); break
    case 'asin': output = Math.asin(value); break
    case 'atan': output = Math.atan(value); break
    case 'abs': output = Math.abs(value); break
    case 'exp': output = Math.exp(value); break
    case 'log': output = Math.log(value); break
    case 'log10': output = Math.log(value) / Math.log(10); break
    case 'sin': output = Math.sin(value); break
    case 'sinh': output = Math.sinh(value); break
    case 'tan': output = Math.tan(value); break
    case 'tanh': output = Math.tanh(value); break
    case 'sqrt': output = Math.sqrt(value); break
    case 'cbrt': output = Math.cbrt(value); break
    case 'cos': output = Math.cos(value); break
    case 'cosh': output = Math.cosh(value); break
    case 'mod': output = value % v2!.value; break
    case 'atan2': output = Math.atan2(value, v2!.value); break
    case 'pow': output = P.cpow(value, v2!.value); break
    case 'hypot': output = Math.sqrt(P.cpow(v1.value, 2) + P.cpow(v2!.value, 2) + (v3 ? P.cpow(v3.value, 2) : 0)); break
    case 'cath': output = Math.sqrt(P.cpow(v1.value, 2) - P.cpow(v2!.value, 2) - (v3 ? P.cpow(v3.value, 2) : 0)); break
    case 'round': output = boostRound(value, 'round'); break
    case 'trunc': output = boostRound(value, 'trunc'); break
    case 'ceil': output = Math.ceil(value); break
    case 'floor': output = Math.floor(value); break
    case 'not': output = asBool(value) ? 0 : 1; break
    default: return fail('ExpressionError', `Unknown function: ${f}`)
  }
  return { t: 'qty', q: { value: scaler * output, dims } }

}

// ─── Vectors, and the checks that come before a matrix, a placement or a rotation ─────────────────────────────

const NEEDS_GEOMETRY = 'Function requires the first argument to be either Matrix, Placement or Rotation.'
/** What the evaluator does not build: a Matrix, a Placement or a Rotation. (scripts/exprdiff.py excuses the cases where FreeCAD
 *  makes one.) */
const notBuilt = (n: Node) => new PyError(inExpr('This evaluator does not build a Matrix, a Placement or a Rotation.', n), 'NotImplementedError')
const L_DIMS: Dims = [1, 0, 0, 0, 0, 0, 0, 0]

/** PyArg_ParseTuple's "d": a number Python can turn into a float (an int, a float, a bool, a Quantity), else null. */
function asDouble(v: PyVal): number | null {
  if (v.t === 'float') return v.v
  if (v.t === 'int' || v.t === 'bool') { const x = Number(v.t === 'int' ? v.v : v.v ? 1n : 0n); return Number.isFinite(x) ? x : null }
  if (v.t === 'qty') return v.q.value
  return null
}
/** VectorPy::PyInit: three floats (fewer are zeros), a Vector, or a list or tuple of three floats; null where Python raises. */
function vectorFromArgs(args: PyVal[]): [number, number, number] | null {
  if (args.length <= 3) {
    const d = args.map(asDouble)
    if (d.every((x) => x !== null)) return [d[0] ?? 0, d[1] ?? 0, d[2] ?? 0]
  }
  if (args.length === 1) {
    const a = args[0]
    if (a.t === 'vector') return [...a.v]
    if (a.t === 'list' || a.t === 'tuple') {
      const d = a.v.map((x) => (x.t === 'float' ? x.v : x.t === 'int' ? Number(x.v) : null))
      if (d.length === 3 && d.every((x) => x !== null)) return d as [number, number, number]
    }
  }
  return null
}
/** extractVectorArgument. */
function vectorArg(n: Extract<Node, { k: 'fn' }>, i: number, env: Env): [number, number, number] {
  const a = ev(n.args[i], env)
  if (a.t !== 'vector') throw new PyError(inExpr('Argument must be a vector.', n), 'ExpressionError')
  return a.v
}
/** extractLengthValueArgument. */
function lengthArg(n: Extract<Node, { k: 'fn' }>, i: number, env: Env): number {
  const q = P.toQuantity(ev(n.args[i], env))
  if (!q) throw new PyError(inExpr('Failed to convert to Quantity.', n), 'TypeError')
  if (!P.isDimless(q.dims) && !P.sameDims(q.dims, L_DIMS)) throw new PyError(inExpr('Unit must be either empty or a length.', n), 'ExpressionError')
  return q.value
}
const toDegrees = (r: number) => r * (180 / pi)
const sqr = P.vecSqr

function evalObjectFunction(n: Extract<Node, { k: 'fn' }>, env: Env): PyVal {
  const f = n.f, args = n.args
  const fail = (cls: string, msg: string): never => { throw new PyError(inExpr(msg, n), cls) }
  const angleOrNone = (q: Quantity) => P.isDimless(q.dims) || P.sameDims(q.dims, P.ANGLE)
  switch (f) {
    case 'vector': return evalVectorInit(args.map((a) => ev(a, env)))
    case 'create': {
      const type = ev(args[0], env)
      if (type.t !== 'str') return fail('ExpressionError', 'Function requires the first argument to be a string.')
      const name = type.v.toLowerCase()
      if (name !== 'matrix' && name !== 'vector' && name !== 'placement' && name !== 'rotation') return fail('ExpressionError', `Unknown type '${type.v}'.`)
      const rest = args.slice(1).map((a) => ev(a, env))
      if (name !== 'vector') throw notBuilt(n)
      return rest.length ? evalVectorInit(rest) : P.vector([0, 0, 0])
    }
    case 'matrix': case 'placement': case 'rotation': args.forEach((a) => ev(a, env)); throw notBuilt(n)
    case 'minvert': ev(args[0], env); return fail('ExpressionError', NEEDS_GEOMETRY)
    case 'mrotate':
      for (let i = 1; i < args.length; i++) ev(args[i], env)
      ev(args[0], env)
      return fail('ExpressionError', NEEDS_GEOMETRY)
    case 'mrotatex': case 'mrotatey': case 'mrotatez': {
      const q = P.toQuantity(ev(args[1], env))
      if (!q) return fail('TypeError', 'Invalid rotation angle.')
      if (!angleOrNone(q)) return fail('ExpressionError', 'Unit must be either empty or an angle.')
      ev(args[0], env)
      return fail('ExpressionError', NEEDS_GEOMETRY)
    }
    case 'mscale': case 'mtranslate': {
      // evaluateSecondVectorArgument: the second argument is a sequence of three numbers, or the next three arguments are
      let values: PyVal[]
      if (args.length === 2) {
        const second = ev(args[1], env)
        const items = sequenceItems(second)
        if (!items) return fail('ExpressionError', `Second parameter is not a sequence type: '${P.pyStr(second)}'.`)
        if (items.length !== 3) return fail('ExpressionError', `Second parameter provided has ${items.length} elements instead of 3.`)
        values = items
      } else {
        values = [ev(args[1], env), ev(args[2], env), ev(args[3], env)]
      }
      if (!values.every((x) => asDouble(x) !== null)) return fail('ExpressionError', 'Error parsing scale values.')
      ev(args[0], env)
      return fail('ExpressionError', NEEDS_GEOMETRY)
    }
    case 'translationm': {
      if (args.length === 1) {
        const p = ev(args[0], env)
        const items = sequenceItems(p)
        if (!items) return fail('ExpressionError', `Not sequence type: '${P.pyStr(p)}'.`)
        if (items.length !== 3) return fail('ExpressionError', `Sequence provided has ${items.length} elements instead of 3.`)
        if (!items.every((x) => asDouble(x) !== null)) return fail('ExpressionError', 'Error parsing sequence.')
        throw notBuilt(n)
      }
      const qs = args.map((a, i) => {
        const q = P.toQuantity(ev(a, env))
        if (!q) return fail('TypeError', `Invalid ${['first', 'second', 'third'][i]} argument.`)
        return q
      })
      if (!qs.every((q) => P.isDimless(q.dims) || P.sameDims(q.dims, L_DIMS))) return fail('ExpressionError', 'Translation units must be a length or dimensionless.')
      throw notBuilt(n)
    }
    case 'rotationx': case 'rotationy': case 'rotationz': {
      const q = P.toQuantity(ev(args[0], env))
      if (!q) return fail('TypeError', 'Invalid first argument.')
      if (!angleOrNone(q)) return fail('ExpressionError', 'Unit must be either empty or an angle.')
      throw notBuilt(n)
    }
  }
  // The vector functions: each argument is taken as it is needed.
  const v1 = vectorArg(n, 0, env)
  switch (f) {
    case 'vnormalize': {
      const len = P.vecLength(v1)
      return P.vector(len !== 0 && len !== 1 ? [v1[0] / len, v1[1] / len, v1[2] / len] : [...v1])
    }
    case 'vscale': return P.vector([v1[0] * lengthArg(n, 1, env), v1[1] * lengthArg(n, 2, env), v1[2] * lengthArg(n, 3, env)])
    case 'vscalex': return P.vector([v1[0] * lengthArg(n, 1, env), v1[1], v1[2]])
    case 'vscaley': return P.vector([v1[0], v1[1] * lengthArg(n, 1, env), v1[2]])
    case 'vscalez': return P.vector([v1[0], v1[1], v1[2] * lengthArg(n, 1, env)])
  }
  const v2 = vectorArg(n, 1, env)
  switch (f) {
    case 'vangle': {
      const len1 = P.vecLength(v1), len2 = P.vecLength(v2)
      let angle: number
      if (len1 <= Number.EPSILON || len2 <= Number.EPSILON) angle = NaN
      else {
        let dot = P.vecDot(v1, v2)
        dot /= len1
        dot /= len2
        angle = dot <= -1 ? pi : dot >= 1 ? 0 : Math.acos(dot)
      }
      return { t: 'qty', q: { value: toDegrees(angle), dims: P.ANGLE } }
    }
    case 'vcross': return P.vector(P.vecCross(v1, v2))
    case 'vdot': return P.float(P.vecDot(v1, v2))
  }
  const v3 = vectorArg(n, 2, env)
  switch (f) {
    case 'vlinedist': return { t: 'qty', q: { value: Math.abs(P.vecLength(P.vecCross(v3, P.vecSub(v1, v2))) / P.vecLength(v3)), dims: L_DIMS } }
    case 'vlinesegdist': { // DistanceToLineSegment(p1 = v2, p2 = v3)
      const len2 = sqr(P.vecSub(v2, v3))
      if (len2 === 0) return P.vector([...v2])
      const p2p1 = P.vecSub(v3, v2), pXp1 = P.vecSub(v1, v2)
      const dot = P.vecDot(pXp1, p2p1)
      const q = dot / len2
      const t = q < 0 ? 0 : 1 < q ? 1 : q
      return P.vector(P.vecSub(P.vecScale(p2p1, t), pXp1))
    }
    case 'vlineproj': { // ProjectToLine(point = v2, line = v3): the answer does not depend on the vector it is called on
      const k = P.vecDot(v2, v3) / sqr(v3)
      return P.vector(P.vecSub(P.vecScale(v3, k), v2))
    }
    case 'vplanedist': return { t: 'qty', q: { value: P.vecDot(P.vecSub(v1, v2), v3) / P.vecLength(v3), dims: L_DIMS } }
    case 'vplaneproj': { // ProjectToPlane(base = v2, normal = v3)
      const k = P.vecDot(P.vecSub(v1, v2), v3) / sqr(v3)
      return P.vector(P.vecSub(v1, P.vecScale(v3, k)))
    }
  }
  return fail('ExpressionError', `Unknown function: ${f}`)
}
function evalVectorInit(args: PyVal[]): PyVal {
  const v = vectorFromArgs(args)
  if (!v) throw P.systemError() // the constructor failed and the call went on with its exception set
  return P.vector(v)
}
/** The items of a sequence Python can iterate (a str, a list, a tuple or a Vector), else null. */
function sequenceItems(v: PyVal): PyVal[] | null {
  if (v.t === 'str') return Array.from(v.v).map((c) => P.str(c))
  if (v.t === 'list' || v.t === 'tuple') return v.v
  if (v.t === 'vector') return v.v.map((x) => P.float(x))
  return null
}

// ─── What the quantity boxes use ───────────────────────────────────────────────────────────────

/** The result as a quantity: a number, a Quantity or a bool; anything else is not a quantity (expressionFromPy gives a
 *  StringExpression or a PyObjectExpression for it, and interpretQuantityInput refuses those). */
export function asQuantity(v: PyVal): Quantity {
  switch (v.t) {
    case 'qty': return v.q
    case 'float': return { value: v.v, dims: ZERO }
    case 'int': return { value: Number(v.v), dims: ZERO }
    case 'bool': return { value: v.v ? 1 : 0, dims: ZERO }
    default: throw new QuantityError('Expression could not be evaluated', 'eval')
  }
}

/** A tree nested deeper than the JavaScript stack (thousands of signs or brackets) stops with the error Python gives for it,
 *  not the engine's own. */
function deep<T>(f: () => T): T {
  try { return f() } catch (e) {
    if (e instanceof RangeError && /call stack/i.test(e.message)) throw new PyError('maximum recursion depth exceeded', 'RecursionError')
    throw e
  }
}
/** Evaluate a tree to a quantity (Expression::eval() and its NumberExpression). */
export function evalNode(n: Node, vars: Record<string, Quantity | PyVal>, owner?: string): Quantity {
  return asQuantity(deep(() => ev(n, { vars, owner })))
}
/** Evaluate an expression (without its leading "=") to a Python value. */
export function evaluateValue(text: string, env: Env): PyVal {
  return deep(() => ev(parseExpr(text, new Set(Object.keys(env.vars)), env.owner), env))
}
/** Evaluate an expression (without its leading "=") to a quantity; `vars` are the names it may use. */
export function evaluate(text: string, vars: Record<string, Quantity | PyVal>, owner?: string): Quantity {
  return evalNode(parseExpr(text, new Set(Object.keys(vars)), owner), vars, owner)
}
/** What Expression Editor shows for a result that is not a number: the text of the expression it becomes (result->toString()). */
export function resultText(v: PyVal): string {
  if (v.t === 'str') return quote(v.v)
  return P.pyStr(v)
}

/** AdditiveOperatorDetector: whether the input has a + or - between terms, anywhere in the tree. */
export function hasAdditive(n: Node): boolean {
  switch (n.k) {
    case 'op': return n.op === '+' || n.op === '-' || hasAdditive(n.l) || hasAdditive(n.r)
    case 'neg': case 'pos': return hasAdditive(n.a)
    case 'fn': return n.args.some(hasAdditive)
    case 'cond': return hasAdditive(n.c) || hasAdditive(n.t) || hasAdditive(n.f)
    case 'var': return n.comps.some((c) => !('name' in c) && [c.e1, c.e2, c.e3].some((e) => e && hasAdditive(e)))
    default: return false
  }
}

/** rewriteOwnerlessQuantityExpression: in a quantity field "1/2 mm" means (1/2) mm. */
export function rewriteOwnerless(n: Node): Node {
  if (n.k === 'neg' || n.k === 'pos') return { ...n, a: rewriteOwnerless(n.a) }
  if (n.k !== 'op') return n
  const l = rewriteOwnerless(n.l), r = rewriteOwnerless(n.r)
  if (n.op === '/' && r.k === 'op' && r.op === 'unit') return { k: 'op', op: '*', l: { k: 'op', op: '/', l, r: r.l }, r: r.r }
  return { ...n, l, r }
}

/** applyDefaultUnitPolicy: at each + or - from the top, a whole term without a unit takes the field's unit; units, products
 *  and powers keep their own meaning. */
export function applyDefaultUnit(n: Node, unit: Quantity, vars: Record<string, Quantity | PyVal> = {}, symbol = ''): Node {
  if (n.k !== 'op' || (n.op !== '+' && n.op !== '-')) return n
  const side = (o: Node): Node => {
    try {
      const q = evalNode(o, vars)
      if (P.isDimless(q.dims)) return { k: 'op', op: 'unit', l: o, r: { k: 'unit', q: unit, s: symbol } }
    } catch { /* a nested sum may need its own terms given the unit first */ }
    return o.k === 'op' && (o.op === '+' || o.op === '-') ? applyDefaultUnit(o, unit, vars, symbol) : o
  }
  return { ...n, l: side(n.l), r: side(n.r) }
}
