// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Gui/QuantitySpinBox.cpp: 2014 Werner Mayer
//   No copyright line in the file: src/App/QuantityInput.cpp
// How a quantity box reads what is typed, ported from App/QuantityInput.cpp and
// Gui/QuantitySpinBox.cpp at FreeCAD main 3160daf1e2b6 (LGPL-2.1-or-later). A bare number
// takes the unit the box shows; "1 in" and "2 m 3 cm" are read as quantities; anything with
// + or - between terms is read as an expression, whose bare terms take the box's unit.
import { parseQuantity, userString, QuantityError, type Quantity } from './quantity'
import { applyDefaultUnit, evalNode, hasAdditive, parseExpr, PyError, rewriteOwnerless, type Node } from './expr'
import type { Dims } from './units-data'

export type InputKind = 'IncompleteNumber' | 'InvalidNumber' | 'ExpressionSyntax' | 'Evaluation' | 'IncompatibleUnit' | 'OutOfRange' | 'MalformedGrouping'
export type InputResult =
  | { status: 'ok'; q: Quantity }
  | { status: 'incomplete' | 'invalid'; kind: InputKind; offset: number; length: number }

/** Gui::numericInputDiagnosticText. MalformedGrouping (App::InputDiagnosticKind, from
 *  Base::scanLocalizedNumber's digit-grouping validation) is unused today: this port has no
 *  thousands-separator grouping concept, so nothing ever produces it. */
export const DIAGNOSTIC: Record<InputKind, string> = {
  IncompleteNumber: 'Incomplete number',
  InvalidNumber: 'Invalid number',
  ExpressionSyntax: 'Invalid expression',
  Evaluation: 'Expression could not be evaluated',
  IncompatibleUnit: 'Incompatible unit',
  OutOfRange: 'Value is outside the allowed range',
  MalformedGrouping: 'Malformed grouping separator placement',
}

const same = (a: Dims, b: Dims) => a.every((d, i) => d === b[i])
const dimensionless = (q: Quantity) => q.dims.every((d) => d === 0)

/** QuantityInputUnit: the unit the box shows, if it parses to the box's dimension; else the
 *  internal unit. Bare numbers are read in it. */
export type DisplayUnit = { scale: Quantity; symbol: string }
export function displayUnitOf(dims: Dims, symbol: string): DisplayUnit {
  const base = { scale: { value: 1, dims }, symbol: '' }
  if (dims.every((d) => d === 0) || !symbol) return base
  try {
    const q = parseQuantity(`1 ${symbol}`)
    return !dimensionless(q) && same(q.dims, dims) ? { scale: q, symbol } : base
  } catch { return base }
}

/** The leading number token, as Base::scanLocalizedNumber reads it: a sign alone, a
 *  trailing "e" or "e-", or a lone point (or a point with nothing after it, "1.") is
 *  incomplete. */
function scanNumber(text: string, at: number): 'ok' | 'incomplete' | 'none' {
  const rest = text.slice(at)
  if (!/^[+\-−]?(\d|\.)/.test(rest) && !/^[+\-−]$/.test(rest)) return 'none'
  const m = /^[+\-−]?(\d+\.?\d*|\.\d+)?([eE][+-]?\d*)?/.exec(rest)!
  const tok = m[0], mant = m[1], exp = m[2]
  const danglingPoint = !!mant && mant.endsWith('.')
  if (tok.length === rest.length && (!mant || danglingPoint || (exp !== undefined && !/\d$/.test(exp)))) return 'incomplete'
  return 'ok'
}

export type InputOptions = { dims: Dims; display: DisplayUnit; min?: number; max?: number; phase: 'editing' | 'commit'; vars?: Record<string, Quantity>
  /** the part the field belongs to (the expression's owner) */
  owner?: string }

/** QuantitySpinBoxPrivate::interpretInput: the quantity grammar first; if that fails as a
 *  syntax error, the expression grammar. */
export function interpretInput(text: string, o: InputOptions): InputResult {
  const first = text.length - text.trimStart().length
  const incomplete = (kind: InputKind, offset = first, length = 1): InputResult => ({ status: o.phase === 'commit' ? 'invalid' : 'incomplete', kind, offset, length })
  const invalid = (kind: InputKind, offset = 0, length = 1): InputResult => ({ status: 'invalid', kind, offset, length })
  if (first === text.length) return incomplete('IncompleteNumber')
  const scan = scanNumber(text, first)
  if (scan === 'incomplete') return incomplete('IncompleteNumber', first, text.length - first)
  const vars = o.vars ?? {}
  const finish = (q: Quantity): InputResult => {
    if (!dimensionless(q) && !same(q.dims, o.dims)) return invalid('IncompatibleUnit')
    if (dimensionless(q) && !dimensionless(o.display.scale)) q = { value: q.value * o.display.scale.value, dims: o.dims }
    if (o.min !== undefined && q.value < o.min) return invalid('OutOfRange')
    if (o.max !== undefined && q.value > o.max) return invalid('OutOfRange')
    return { status: 'ok', q }
  }
  // Quantity grammar (Base::Quantity::parseUserInput); sums go to the expression grammar.
  let additive = false
  try { additive = hasAdditive(parseExpr(text, new Set(Object.keys(vars)), o.owner)) } catch { additive = false }
  if (!additive) {
    try { return finish(parseQuantity(text)) } catch (e) {
      if (e instanceof QuantityError && e.kind === 'mismatch') return invalid('IncompatibleUnit')
      if (!(e instanceof QuantityError && e.kind === 'syntax')) return invalid('Evaluation')
    }
  }
  // Expression grammar, with the field's unit given to its bare terms.
  let tree
  // a text the grammar refuses is a syntax error (Base::ParserError); other exceptions of the parser (a number too big, a call with the wrong number of arguments) are failures to evaluate
  try { tree = rewriteOwnerless(parseExpr(text, new Set(Object.keys(vars)), o.owner)) } catch (e) { return invalid(e instanceof PyError && e.etype !== 'ParserError' ? 'Evaluation' : 'ExpressionSyntax', first) }
  const unit = o.display.scale
  if (!dimensionless(unit)) tree = applyDefaultUnit(tree, unit, vars, o.display.symbol)
  try {
    let q = evalNode(tree, vars, o.owner)
    if (dimensionless(q) && !dimensionless(unit)) q = { value: q.value * unit.value, dims: unit.dims }
    if (!Number.isFinite(q.value)) return invalid('Evaluation')
    return finish(q)
  } catch (e) {
    return invalid(e instanceof QuantityError && e.kind === 'mismatch' ? 'IncompatibleUnit' : 'Evaluation')
  }
}

/** QuantitySpinBox::isNormalized: the text is the value as the schema writes it, or a plain
 *  (signed) number with or without a unit, which Enter leaves as typed. The checks are the C++'s on
 *  the expression classes: a NumberExpression is a number or a constant, and UnitExpression is
 *  what a unit, a number, an operator, a function and a name all derive from. */
export function isNormalized(text: string, shown: string): boolean {
  if (text === shown) return true
  try {
    const isNumber = (x: Node) => x.k === 'num' || x.k === 'const'
    const isUnitExpression = (x: Node) => x.k !== 'str' && x.k !== 'cond' && x.k !== 'range'
    const isSign = (x: Node): x is Extract<Node, { k: 'neg' | 'pos' }> => x.k === 'neg' || x.k === 'pos'
    const n = parseExpr(text)
    if (isNumber(n)) return true // plain numbers
    if (n.k === 'op' && n.op === 'unit' && isUnitExpression(n.r) && isNumber(n.l)) return true // numbers without a sign, with a unit
    if (!isSign(n)) return false
    if (isNumber(n.a)) return true // numbers with a sign, without a unit
    const inner = n.a
    if (inner.k !== 'op' || inner.op !== 'unit' || !isUnitExpression(inner.r)) return false
    if (isNumber(inner.l)) return true // numbers with a sign and a unit
    return isSign(inner.l) && isNumber(inner.l.a)
  } catch { /* not a plain number */ }
  return false
}

/** QuantitySpinBox::selectNumber: how much of the text is the number. */
export function numberLength(text: string): number {
  return /^[+\-−]?(\d+\.?\d*|\.\d+)([eE][+-]?\d+)?/.exec(text)?.[0].length ?? 0
}

/** getUserString, and the unit it shows the value in. `decimals`, if given, overrides the
 *  schema's own decimal count (QuantitySpinBox::setDecimals). */
export function shownText(q: Quantity, decimals?: number): { text: string; display: DisplayUnit } {
  const u = userString(q, undefined, decimals)
  return { text: u.text, display: displayUnitOf(q.dims, u.unit) }
}
