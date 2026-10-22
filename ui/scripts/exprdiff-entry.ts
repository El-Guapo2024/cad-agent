// SPDX-License-Identifier: LGPL-2.1-or-later
// What scripts/exprdiff.py runs through Node: our evaluator on an expression, the answer written the way scripts/exprdiff_fc.py
// writes FreeCAD's (exprdiff.py describes the form: {t:'quantity', v, dims}, {t:'int', v:'3'}, {t:'str', v}, {t:'list', v:[...]},
// or {error, etype}; nan, inf and -0.0 as strings).
//
// This entry is for src/expr.ts as it stands: its answers are Quantities only, so run exprdiff.py with --loose (numbers and units;
// an error where FreeCAD answers, or an answer where FreeCAD raises, still counts). Once the evaluator gives Python values (ints,
// floats, strings, lists ...) make run() describe them all in that form, name the exception classes FreeCAD raises in etype, and
// leave --loose out. The properties are those of exprdiff_cases.PROPERTIES (the answers file records them): the ones a Quantity holds.
import { evaluate } from '../src/expr'
import type { Dims } from '../src/units-data'

const Z: Dims = [0, 0, 0, 0, 0, 0, 0, 0]
const L: Dims = [1, 0, 0, 0, 0, 0, 0, 0]
const ENV = {
  pLen: { value: 10, dims: L }, pWid: { value: 20, dims: L }, pAng: { value: 30, dims: [0, 0, 0, 0, 0, 0, 0, 1] as Dims },
  pMass: { value: 2, dims: [0, 1, 0, 0, 0, 0, 0, 0] as Dims }, pCnt: { value: 3, dims: Z }, pRat: { value: 0.5, dims: Z },
}
const enc = (x: number) => (Number.isNaN(x) ? 'nan' : x === Infinity ? 'inf' : x === -Infinity ? '-inf' : Object.is(x, -0) ? '-0.0' : x)

export function run(text: string) {
  try {
    const q = evaluate(text, ENV)
    return { t: 'quantity', v: enc(q.value), dims: q.dims }
  } catch (e) {
    return { error: (e as Error).message, etype: (e as Error).constructor.name }
  }
}
