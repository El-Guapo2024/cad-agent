// SPDX-License-Identifier: LGPL-2.1-or-later
// What scripts/exprdiff.py runs through Node: our evaluator on an expression, the answer written the way
// scripts/exprdiff_fc.py writes FreeCAD's. The owner's properties are those exprdiff_cases.PROPERTIES lists (the answers file records them).
import { evaluateValue, PyError, type PyVal } from '../src/expr'
import { QUIRKS } from '../src/expr-py'
import { QuantityError } from '../src/quantity'

// FreeCAD's integer-valued numbers above 2^31 come out as -2147483648 (a cast in essentiallyInteger); the comparison
// wants every other answer to agree, so it switches that on.
QUIRKS.int32Cast = true

const L = [1, 0, 0, 0, 0, 0, 0, 0] as const
const env = {
  vars: {
    pLen: { t: 'qty', q: { value: 10, dims: [...L] } },
    pWid: { t: 'qty', q: { value: 20, dims: [...L] } },
    pAng: { t: 'qty', q: { value: 30, dims: [0, 0, 0, 0, 0, 0, 0, 1] } },
    pMass: { t: 'qty', q: { value: 2, dims: [0, 1, 0, 0, 0, 0, 0, 0] } },
    pCnt: { t: 'int', v: 3n },
    pRat: { t: 'float', v: 0.5 },
    pStr: { t: 'str', v: 'abc' },
    pOn: { t: 'bool', v: true },
    pLong: { t: 'str', v: 'abcdefghij' },
    pList: { t: 'list', v: ['a', 'b', 'c', 'd', 'e', 'f'].map((v) => ({ t: 'str', v })) },
  } as Record<string, PyVal>,
  owner: 'Obj',
  doc: 'T',
}

const enc = (x: number): number | string => (Number.isNaN(x) ? 'nan' : x === Infinity ? 'inf' : x === -Infinity ? '-inf' : Object.is(x, -0) ? '-0.0' : x)

type Described = Record<string, unknown>
export function describe(r: PyVal): Described {
  switch (r.t) {
    case 'none': return { t: 'none' }
    case 'bool': return { t: 'bool', v: r.v }
    case 'int': return { t: 'int', v: r.v.toString() }
    case 'float': return { t: 'float', v: enc(r.v) }
    case 'complex': return { t: 'complex', re: enc(r.re), im: enc(r.im) }
    case 'str': return { t: 'str', v: r.v }
    case 'qty': return { t: 'quantity', v: enc(r.q.value), dims: [...r.q.dims] }
    case 'list': case 'tuple': return { t: r.t, v: r.v.map(describe) }
    case 'obj': return { t: 'other', type: r.type, str: r.str }
    case 'vector': return { t: 'vector', v: r.v.map(enc) }
  }
}

export function run(text: string): Described {
  try {
    return describe(evaluateValue(text, env))
  } catch (e) {
    if (e instanceof PyError) return { error: e.message, etype: e.etype }
    if (e instanceof QuantityError) return { error: e.message, etype: 'QuantityError' }
    return { error: `${(e as Error).name}: ${(e as Error).message}`, etype: 'Crash' }
  }
}
