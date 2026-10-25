// SPDX-License-Identifier: LGPL-2.1-or-later
// The entry tests/golden/sketchcurves/engine.mjs is bundled from (ui/scripts/sketchcurves-bundle.sh): the Sketcher's
// curve tools (ui/src/sketchbspline.ts, the B-spline paths of sketchops.ts) on a case of
// tests/golden/sketchcurves/freecad.json, its answer in the shape tests/golden/sketchops/freecad_side.py records
// FreeCAD's. The sketch kernel's answers come from a cache (tests/golden/sketchcurves/make.py fills it from
// cad_agent/sketch_kernel.py); a case that needs an answer the cache has not got reports the request instead.
import type { Geo, XY } from '../src/solver'
import * as SK from '../src/sketch'
import * as OPS from '../src/sketchops'
import * as BS from '../src/sketchbspline'
import { cached, KernelNeeded, type KAnswer, type KReq } from '../src/sketchkernel'
import * as CC from '../src/sketchcarbon'

type Case = { geometry: Geo[]; constraints: (unknown[])[]; expose?: number[]; op: [string, unknown[]] }
type SolveFn = (json: string) => { status_code: number; stored_geometry: Geo[] }

const DIMENSIONAL = ['Distance', 'DistanceX', 'DistanceY', 'Radius', 'Diameter', 'Angle', 'Weight']
function toConstraint(a: unknown[]): SK.Constraint {
  const type = a[0] as string, rest = a.slice(1) as number[]
  if (DIMENSIONAL.includes(type)) return SK.fromCons({ type, args: rest.slice(0, -1), value: rest[rest.length - 1] })
  return SK.fromCons({ type, args: rest })
}
function out(c: SK.Constraint) {
  const d: Record<string, unknown> = { type: c.type, elements: [c.first, c.firstPos, c.second, c.secondPos, c.third, c.thirdPos] }
  if (c.type === 'InternalAlignment') { d.alignment = c.alignment ?? 'Undef'; d.index = c.alignmentIndex ?? -1 }
  if (DIMENSIONAL.includes(c.type)) d.value = c.value
  return d
}
/** One case with the kernel answers in `answers` (by request): its result, or the requests it still needs. */
export function runCase(c: Case, solve: SolveFn, answers: Map<string, KAnswer>): { result?: unknown; needs?: KReq[] } {
  const doc: OPS.Doc = { geometry: c.geometry.map((g) => ({ ...g })), constraints: c.constraints.map(toConstraint) }
  const k = cached(answers)
  const move: OPS.Mover = (d, geo, pos, to) => {
    const r = solve(JSON.stringify({ geometry: d.geometry, constraints: d.constraints.map(SK.toCons), solve: false,
      drags: [{ geo, pos, to, update_geometry: true }] }))
    return r.status_code === 0 ? r.stored_geometry : null
  }
  for (const g of c.expose ?? []) BS.exposeInternalGeometry(doc, g)
  const [op, args] = c.op
  let ok: boolean | string = true
  try {
    let done = true
    if (op === 'convert') {
      const ids = args[0] as number[]
      for (const g of ids) if (!BS.convertToNURBS(doc, g, k)) done = false
      if (done) for (const g of ids) BS.exposeInternalGeometry(doc, g)
    } else if (op === 'degree_up') {
      const [g] = args as [number]
      done = BS.increaseBSplineDegree(doc, g, k)
      if (done) BS.exposeInternalGeometry(doc, g)
    } else if (op === 'degree_down') {
      BS.decreaseBSplineDegree(doc, (args as [number])[0], k) // Python's decreaseBSplineDegree hands back a bool
    } else if (op === 'knot_mult') {
      const [g, i, inc] = args as [number, number, number]
      const ng = BS.modifyBSplineKnotMultiplicity(doc, g, i, inc, k)
      BS.exposeInternalGeometry(doc, ng)
    } else if (op === 'insert_knot') {
      const [g, u, m] = args as [number, number, number]
      const ng = BS.insertBSplineKnot(doc, g, u, m, k)
      BS.exposeInternalGeometry(doc, ng)
    } else if (op === 'join') {
      const [g1, p1, g2, p2, cont] = args as [number, SK.PointPos, number, SK.PointPos, number]
      done = BS.join(doc, g1, p1, g2, p2, cont, k)
    } else if (op === 'trim') { const [g, p, axes] = args as [number, XY, boolean]; done = OPS.trim(doc, g, p, axes, k) }
    else if (op === 'split') { const [g, p] = args as [number, XY]; done = OPS.split(doc, g, p, k) }
    else if (op === 'fillet') {
      const [g1, g2, r1, r2, rad, trim, corner, chamfer] = args as [number, number, XY, XY, number, boolean, boolean, boolean]
      done = OPS.fillet(doc, g1, g2, r1, r2, rad, trim, corner, chamfer, move, k)
    } else if (op === 'bspline_by_knots') {
      const [pts, mults, periodic, construction] = args as [XY[], number[], boolean, boolean]
      const first = doc.geometry.length
      doc.geometry = [...doc.geometry, ...pts.map(BS.knotPoint)]
      BS.bsplineByKnots(doc, first, pts, mults, periodic, construction, k)
    } else if (op === 'carbon_copy') {
      // isCarbonCopyAllowed's placement checks, carbonCopy, then its solve()
      const [geometry, constraints, selfPl, srcPl, construction] = args as [Geo[], unknown[][], CC.Placement, CC.Placement, boolean]
      const ok = CC.carbonCopyAllowed(selfPl, srcPl)
      if ('reason' in ok) done = false
      else {
        CC.carbonCopy(doc, { geometry: geometry.map((g) => ({ ...g })), constraints: constraints.map(toConstraint) }, selfPl, ok.xinv, ok.yinv, construction, 2)
        const r = solve(JSON.stringify({ geometry: doc.geometry, constraints: doc.constraints.map(SK.toCons) }))
        if (r.status_code === 0) doc.geometry = r.stored_geometry
      }
    } else throw new Error(`unknown op ${op}`)
    if (!done) ok = 'refused'
  } catch (e) {
    if (e instanceof KernelNeeded) return { needs: e.reqs }
    ok = String(e)
  }
  return { result: {
    ok,
    // a B-spline's weights read as Part.BSplineCurve.getWeights() gives them: all 1 when the curve is not rational
    geometry: doc.geometry.map((g) => {
      const { construction: _c, ...rest } = g as Geo & { construction?: boolean }
      void _c
      if (rest.type === 'ArcOfCircle') {
        // as freecad_side.py's read_ccw: the start in [0, 2pi)
        const a1 = rest.start_angle - Math.floor(rest.start_angle / (2 * Math.PI)) * 2 * Math.PI
        return { ...rest, start_angle: a1, end_angle: a1 + (rest.end_angle - rest.start_angle) }
      }
      return rest.type === 'BSplineCurve' && !rest.weights ? { ...rest, weights: rest.poles.map(() => 1) } : rest
    }),
    constructions: doc.geometry.map((g) => !!g.construction),
    constraints: doc.constraints.map(out),
  } }
}
