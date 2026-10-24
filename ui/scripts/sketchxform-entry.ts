// SPDX-License-Identifier: LGPL-2.1-or-later
// The entry tests/golden/sketchxform/engine.mjs is bundled from (ui/scripts/sketchxform-bundle.sh): ui/src/sketchxform.ts's
// addSymmetric, addCopy, addMove, addRectangularArray and removeAxesAlignment on a case of
// tests/golden/sketchxform/freecad.json, started from the sketch FreeCAD had before the operation (its "input"), the
// answer in the shape tests/golden/sketchxform/freecad_side.py records FreeCAD's.
import type { Geo, XY } from '../src/solver'
import * as SK from '../src/sketch'
import * as XF from '../src/sketchxform'

type Recorded = { type: SK.ConstraintType; elements: number[]; alignment?: string; index?: number; value?: number; name: string; driving: boolean }
type State = { geometry: (Geo & { start_point?: XY; end_point?: XY })[]; constructions: boolean[]; constraints: Recorded[] }
type Case = { op: [string, unknown[]]; freecad: { input?: State; error?: string } }

const DIMENSIONAL = ['Distance', 'DistanceX', 'DistanceY', 'Radius', 'Diameter', 'Angle', 'Weight']
function toConstraint(r: Recorded): SK.Constraint {
  const [f, fp, s, sp, t, tp] = r.elements
  const c = SK.constraint(r.type, f, fp as SK.PointPos, s, sp as SK.PointPos, t, tp as SK.PointPos, DIMENSIONAL.includes(r.type) ? r.value ?? 0 : 0)
  if (r.type === 'InternalAlignment') { c.alignment = r.alignment as SK.Constraint['alignment']; c.alignmentIndex = r.index ?? -1 }
  c.name = r.name
  c.driving = r.driving
  return c
}
function out(c: SK.Constraint) {
  const d: Record<string, unknown> = { type: c.type, elements: [c.first, c.firstPos, c.second, c.secondPos, c.third, c.thirdPos], name: c.name, driving: c.driving }
  if (c.type === 'InternalAlignment') { d.alignment = c.alignment ?? 'Undef'; d.index = c.alignmentIndex ?? -1 }
  if (DIMENSIONAL.includes(c.type)) d.value = c.value
  return d
}
export function runCase(c: Case) {
  const input = c.freecad.input
  if (!input) return { error: 'FreeCAD could not make the sketch' }
  const geometry = input.geometry.map((g, i) => {
    const { start_point: _s, end_point: _e, ...rest } = g
    void _s; void _e
    return (input.constructions[i] ? { ...rest, construction: true } : rest) as Geo
  })
  const doc: XF.Doc = { geometry, constraints: input.constraints.map(toConstraint) }
  const [op, args] = c.op
  let ok: boolean | string = true
  try {
    if (op === 'symmetric') { const [ids, ref, pos] = args as [number[], number, SK.PointPos]; XF.addSymmetric(doc, ids, ref, pos) }
    else if (op === 'copy') { const [ids, v, clone] = args as [number[], XY, boolean]; XF.addCopy(doc, ids, v, false, clone) }
    else if (op === 'move') { const [ids, v] = args as [number[], XY]; XF.addMove(doc, ids, v) }
    else if (op === 'array') { const [ids, v, clone, rows, cols, disp, perp] = args as [number[], XY, boolean, number, number, boolean, number]; XF.addRectangularArray(doc, ids, v, clone, rows, cols, disp, perp) }
    else if (op === 'removeAxes') { const [ids] = args as [number[]]; XF.removeAxesAlignment(doc, ids) }
  } catch (e) { ok = String(e) }
  return {
    ok,
    geometry: doc.geometry.map((g) => { const { construction: _c, ...rest } = g as Geo & { construction?: boolean }; void _c; return rest }),
    constructions: doc.geometry.map((g) => !!g.construction),
    constraints: doc.constraints.map(out),
  }
}
