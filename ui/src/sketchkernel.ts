// SPDX-License-Identifier: LGPL-2.1-or-later
// The OpenCascade numbers the Sketcher's curve tools need (a B-spline's new poles after a degree or knot change, the
// conversion of a curve to NURBS, a B-spline's trim, a fillet between curves, an offset, an interpolation), from the
// server: `cad feature sketchkernel` runs the same OCCT calls FreeCAD's Part::Geom* classes make, on the same OCCT
// (cad_agent/sketch_kernel.py). The operations themselves (SketchObject's bookkeeping of geometry and constraints)
// stay in the page, written as plain functions of a sketch; when one needs an answer it has not got, it throws
// KernelNeeded, withKernel fetches the answer and runs the function again from the start. The answers are cached by
// request, so a function runs at most once per answer it needs (and the cache serves a repeat at once).
import type { Geo, XY } from './solver'

export type KReq =
  | { op: 'nurbs'; geo: Geo }
  | { op: 'degree'; geo: Geo; degree: number }
  | { op: 'approximate'; geo: Geo; degree: number }
  | { op: 'multiplicity'; geo: Geo; index: number; mult: number }
  | { op: 'insert_knot'; geo: Geo; u: number; mult: number }
  | { op: 'trim'; geo: Geo; u: number; v: number }
  | { op: 'closest'; geo: Geo; p: XY }
  | { op: 'seek'; geometry: Geo[]; id: number; p: XY; axes: boolean }
  | { op: 'fillet'; geo1: Geo; geo2: Geo; ref1: XY; ref2: XY; radius: number }
  | { op: 'join'; geo1: Geo; pos1: number; geo2: Geo; pos2: number; continuity: number }
  | { op: 'interpolate'; points: XY[]; periodic: boolean; degree: number | null }
  | { op: 'offset'; [k: string]: unknown }
export type KAnswer = { error?: string; geo?: Geo; u?: number; [k: string]: unknown }
/** A function's request for answers it has not got: withKernel catches it. */
export class KernelNeeded extends Error {
  constructor(readonly reqs: KReq[]) { super('kernel answers needed') }
}
/** What the server refused (OCCT's or FreeCAD's message). */
export class KernelError extends Error {}
export type Kernel = (req: KReq) => KAnswer
/** A cache of answers by request. */
export type KCache = Map<string, KAnswer>
const keyOf = (r: KReq) => JSON.stringify(r)

/** The answer to req from the cache; throws KernelNeeded when it is not there, KernelError when it was refused. */
export function cached(cache: KCache): Kernel {
  return (req) => {
    const a = cache.get(keyOf(req))
    if (!a) throw new KernelNeeded([req])
    if (a.error !== undefined) throw new KernelError(a.error)
    return a
  }
}
/** As cached, but a refusal is handed back as {error} instead of thrown. */
export function answerOf(k: Kernel, req: KReq): KAnswer {
  try { return k(req) } catch (e) { if (e instanceof KernelError) return { error: e.message }; throw e }
}
export type Fetch = (reqs: KReq[]) => Promise<KAnswer[]>
/** fn run with the kernel's answers: each time it asks for one it has not got, the answer is fetched and fn runs
 *  again. fn must start from its inputs each time (it is run more than once). */
export async function withKernel<T>(fn: (k: Kernel) => T, fetch: Fetch = serverFetch, cache: KCache = shared): Promise<T> {
  for (let round = 0; round < 64; round++) {
    try { return fn(cached(cache)) } catch (e) {
      if (!(e instanceof KernelNeeded)) throw e
      const answers = await fetch(e.reqs)
      e.reqs.forEach((r, i) => cache.set(keyOf(r), answers[i] ?? { error: 'no answer' }))
    }
  }
  throw new Error('the sketch kernel was asked too many times')
}
/** An operation the page runs at once when the kernel's answers it needs are at hand (any but a B-spline's, usually),
 *  else as soon as they are: done(result) or fail(error) either way. fn must start from its inputs each time. */
export function runOp<T>(fn: (k: Kernel) => T, done: (r: T) => void, fail: (e: unknown) => void, cache: KCache = shared) {
  let r: T
  try { r = fn(cached(cache)) } catch (e) {
    if (!(e instanceof KernelNeeded)) { fail(e); return }
    withKernel(fn, serverFetch, cache).then(done, fail)
    return
  }
  done(r)
}
/** fn run without waiting: its result, or null when it needs an answer it has not got (the request is then sent, and
 *  then() runs once it is in: a preview drawn on the next mouse move, say). */
export function tryKernel<T>(fn: (k: Kernel) => T, then?: () => void, cache: KCache = shared): T | null {
  try { return fn(cached(cache)) } catch (e) {
    if (!(e instanceof KernelNeeded)) throw e
    const key = keyOf(e.reqs[0])
    if (!pending.has(key)) {
      pending.add(key)
      void serverFetch(e.reqs).then((answers) => {
        e.reqs.forEach((r, i) => cache.set(keyOf(r), answers[i] ?? { error: 'no answer' }))
        pending.delete(key)
        then?.()
      }, () => pending.delete(key))
    }
    return null
  }
}
const pending = new Set<string>()
const shared: KCache = new Map()
let server: Fetch = async () => { throw new Error('no sketch kernel') }
/** How the page reaches `cad feature sketchkernel` (sketchkernelapi.ts sets it). */
export function setKernelFetch(f: Fetch) { server = f }
let inFlight = 0
/** The requests on their way (a check waits for none before it reads the sketch). */
export const kernelBusy = () => inFlight
const serverFetch: Fetch = async (reqs) => { inFlight++; try { return await server(reqs) } finally { inFlight-- } }
