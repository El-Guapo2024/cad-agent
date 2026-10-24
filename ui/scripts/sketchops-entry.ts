// SPDX-License-Identifier: LGPL-2.1-or-later
// The entry tests/golden/sketchops/engine.mjs is bundled from (ui/scripts/sketchops-bundle.sh): ui/src/sketchops.ts's
// trim, split, extend and fillet on a case of tests/golden/sketchops/freecad.json, its answer in the shape
// tests/golden/sketchops/freecad_side.py records FreeCAD's. The solver (for the moves of extend and fillet) is passed in.
import type { Geo, XY } from '../src/solver'
import * as SK from '../src/sketch'
import * as OPS from '../src/sketchops'

type Case = { geometry: Geo[]; constraints: (unknown[])[]; op: [string, unknown[]] }
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
export function runCase(c: Case, solve: SolveFn) {
  const doc: OPS.Doc = { geometry: c.geometry.map((g) => ({ ...g })), constraints: c.constraints.map(toConstraint) }
  const move: OPS.Mover = (d, geo, pos, to) => {
    const r = solve(JSON.stringify({ geometry: d.geometry, constraints: d.constraints.map(SK.toCons), solve: false,
      drags: [{ geo, pos, to, update_geometry: true }] }))
    return r.status_code === 0 ? r.stored_geometry : null
  }
  const [op, args] = c.op
  let ok: boolean | string = true
  try {
    let done = false
    if (op === 'trim') { const [g, p, axes] = args as [number, XY, boolean]; done = OPS.trim(doc, g, p, axes) }
    else if (op === 'split') { const [g, p] = args as [number, XY]; done = OPS.split(doc, g, p) }
    else if (op === 'extend') { const [g, inc, pos] = args as [number, number, SK.PointPos]; done = OPS.extend(doc, g, inc, pos, move) }
    else if (op === 'fillet') { const [g1, g2, r1, r2, rad, trim, corner, chamfer] = args as [number, number, XY, XY, number, boolean, boolean, boolean]; done = OPS.fillet(doc, g1, g2, r1, r2, rad, trim, corner, chamfer, move) }
    else if (op === 'fillet_point') { const [g, pos, rad, trim, corner, chamfer] = args as [number, SK.PointPos, number, boolean, boolean, boolean]; done = OPS.filletAtPoint(doc, g, pos, rad, trim, corner, chamfer, move) }
    if (!done) ok = 'refused'
  } catch (e) { ok = String(e) }
  return {
    ok,
    geometry: doc.geometry.map((g) => { const { construction: _c, ...rest } = g as Geo & { construction?: boolean }; void _c; return rest }),
    constructions: doc.geometry.map((g) => !!g.construction),
    constraints: doc.constraints.map(out),
  }
}
