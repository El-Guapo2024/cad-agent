// SPDX-License-Identifier: LGPL-2.1-or-later
// The page's formula engine (src/expr.ts, quantity.ts, expr-py.ts) for the server: ui/scripts/fcexprjs.py bundles this into
// cad_agent/fcexpr_engine.js, which cad_agent/fcexpr.py runs in V8 (mini-racer), so the server and the browser evaluate a
// spreadsheet's cells and a part's bound parameters with the one engine. Every call takes and gives a JSON text; numbers
// JSON cannot hold travel as {"$f": "nan" | "inf" | "-inf" | "-0"}, Python ints as {"$i": "123"}.
import { evaluateValue, ev, isTokenAConstant, isTokenAUnit, parseExpr, parseUnit, PyError, toText, type Env, type Node, type PyVal, type Ref, type VarPath } from '../src/expr'
import { pyStr, QUIRKS } from '../src/expr-py'
import { QuantityError, toNumber, userString, type Quantity } from '../src/quantity'

// A bare V8 has no TextEncoder or TextDecoder (unquote in expr.ts uses them): UTF-8 through the URI functions, which (like
// a fatal TextDecoder) refuse bytes that are not UTF-8.
const g = globalThis as unknown as Record<string, unknown>
if (typeof g.TextEncoder === 'undefined') {
  g.TextEncoder = class {
    encode(s: string): Uint8Array {
      const bin = unescape(encodeURIComponent((s as unknown as { toWellFormed(): string }).toWellFormed()))
      return Uint8Array.from(bin, (c) => c.charCodeAt(0))
    }
  }
  g.TextDecoder = class {
    decode(b: Uint8Array): string {
      try { return decodeURIComponent(Array.from(b, (x) => '%' + x.toString(16).padStart(2, '0')).join('')) } catch {
        throw new TypeError('The encoded data was not valid for encoding utf-8')
      }
    }
  }
}

type J = unknown
const replacer = (_k: string, v: unknown): unknown => {
  if (typeof v === 'bigint') return { $i: v.toString() }
  if (typeof v === 'number' && (!Number.isFinite(v) || Object.is(v, -0))) return { $f: Number.isNaN(v) ? 'nan' : v === Infinity ? 'inf' : v === -Infinity ? '-inf' : '-0' }
  return v
}
const reviver = (_k: string, v: unknown): unknown => {
  if (v && typeof v === 'object' && !Array.isArray(v)) {
    const o = v as Record<string, unknown>
    if (typeof o.$i === 'string' && Object.keys(o).length === 1) return BigInt(o.$i)
    if (typeof o.$f === 'string' && Object.keys(o).length === 1) return o.$f === 'nan' ? NaN : o.$f === 'inf' ? Infinity : o.$f === '-inf' ? -Infinity : -0
  }
  return v
}
const decode = (text: string): any => JSON.parse(text, reviver) // eslint-disable-line @typescript-eslint/no-explicit-any
const encode = (x: J): string => JSON.stringify(x, replacer)

function fail(e: unknown): J {
  if (e instanceof PyError) return { error: e.message, etype: e.etype, kind: e.kind }
  if (e instanceof QuantityError) return { error: e.message, etype: 'QuantityError', kind: e.kind }
  if (e instanceof RangeError && /call stack/i.test(e.message)) return { error: 'maximum recursion depth exceeded', etype: 'RecursionError', kind: 'eval' }
  return { error: `${(e as Error).name}: ${(e as Error).message}`, etype: 'Crash', kind: 'eval' }
}
const guard = (f: () => J): string => { try { return encode({ ok: f() }) } catch (e) { return encode(fail(e)) } }

/** A path whose `Name.prop` the caller decides after the parse (its resolveAmbiguity runs in Python): it reads as expr.ts's
 *  own default meanwhile, and `amb` says what was written and how many of the names are the default's. */
const deferred = (obj: Ref, prop: string, owner?: string): VarPath => {
  const names = obj.name === owner ? [prop] : [obj.name, prop]
  return { doc: null, obj: null, local: false, names, sub: [], amb: { obj, prop, n: names.length } } as VarPath
}

type Cell = { addr: string; value: PyVal | Quantity; kind?: string }
/** The env Python sends: the owner's properties the tree reads, and per path (by its `id`) and range what the document
 *  resolved, or the error it raised there. */
function env(j: any): Env { // eslint-disable-line @typescript-eslint/no-explicit-any
  const resolved: Record<string, any> = j.resolved ?? {}, ranges: Record<string, any> = j.ranges ?? {} // eslint-disable-line @typescript-eslint/no-explicit-any
  const thrown = (r: { error: string; etype: string; kind?: string }) => new PyError(r.error, r.etype, (r.kind ?? 'eval') as PyError['kind'])
  return {
    vars: j.vars ?? {}, owner: j.owner ?? undefined, doc: j.doc ?? undefined,
    resolve: (p) => {
      const r = resolved[(p as VarPath & { id?: number }).id ?? -1]
      if (!r) return null
      if (r.error !== undefined) throw thrown(r)
      return { value: r.value, rest: r.rest }
    },
    rangeCells: (n) => {
      const r = ranges[(n as Node & { id?: number }).id ?? -1]
      if (!r) return null
      if (!Array.isArray(r)) throw thrown(r)
      return r as Cell[]
    },
  }
}

const api = {
  parse: (text: string, names: string[], owner: string | null, defer: boolean) =>
    guard(() => parseExpr(text, new Set(names), owner ?? undefined, defer ? deferred : undefined)),
  toText: (node: string) => guard(() => toText(decode(node))),
  evaluate: (node: string, e: string) => guard(() => ev(decode(node), env(decode(e)))),
  evaluateText: (text: string, e: string) => guard(() => evaluateValue(text, env(decode(e)))),
  parseUnit: (text: string) => guard(() => parseUnit(text)),
  isTokenAUnit: (s: string) => guard(() => isTokenAUnit(s)),
  isTokenAConstant: (s: string) => guard(() => isTokenAConstant(s)),
  pyStr: (v: string) => guard(() => pyStr(decode(v))),
  userString: (q: string, schema: number, decimals: number, denominator: number) =>
    guard(() => { const r = userString(decode(q), schema ?? undefined, decimals ?? undefined, denominator ?? undefined); return [r.text, r.factor, r.unit] }),
  toNumber: (v: string, format: 'Fixed' | 'Scientific' | 'Default', precision: number) => guard(() => toNumber(decode(v), format, precision)),
  setInt32Cast: (on: boolean) => { QUIRKS.int32Cast = on; return encode({ ok: true }) },
}
;(globalThis as unknown as { FCExpr: typeof api }).FCExpr = api
