// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Sketcher/Gui/CommandConstraints.cpp: 2010 Jürgen Riegel
//   src/Mod/Sketcher/Gui/ViewProviderSketch.cpp: 2009 Juergen Riegel
// The Sketcher's constraint commands (CommandConstraints.cpp): each takes the selection in the order it was made
// (CmdSketcherConstraint::activated with getSelectionEx), or, with nothing selected, starts the selection tool
// (DrawSketchHandlerGenConstraint) that collects clicks until one of the command's allowed sequences is complete. A
// new dimension gets its label placed (LinearDatumLabelPlacement, AngularDatumLabelPlacement) and the datum dialog.
import type { XY } from './solver'
import * as SK from './sketch'
import { type Constraint, type PointPos, NONE, START, END, MID, GEO_UNDEF, H_AXIS, V_AXIS, constraint } from './sketch'
import * as S from './sketcher'
import { report } from './store'

/** A selected element as getIdsFromName gives it: an edge (pos none), a point (its pos), the root (-1, start). */
export type SelId = { geoId: number; pos: PointPos }
const isVertex = (s: SelId) => s.pos !== NONE
const isEdge = (s: SelId) => s.pos === NONE && s.geoId !== GEO_UNDEF
const isRoot = (s: SelId) => s.geoId === -1 && s.pos === START
const isAxis = (s: SelId) => (s.geoId === H_AXIS || s.geoId === V_AXIS) && s.pos === NONE
/** getIdsFromName. */
export function idOf(name: string): SelId | null {
  if (name === 'RootPoint') return { geoId: -1, pos: START }
  if (name === 'H_Axis') return { geoId: H_AXIS, pos: NONE }
  if (name === 'V_Axis') return { geoId: V_AXIS, pos: NONE }
  if (name.startsWith('Edge')) return { geoId: Number(name.slice(4)) - 1, pos: NONE }
  if (name.startsWith('Vertex')) { const [g, p] = S.geoVertexIndex(Number(name.slice(6)) - 1); return { geoId: g, pos: p } }
  return null
}
const selection = (): SelId[] => S.getSelection().map(idOf).filter((x): x is SelId => !!x)
const geo = (g: number) => S.getGeometry()[g]
const P = (s: SelId) => S.getPoint(s.geoId, s.pos)!
const warn = (title: string, text: string) => report('warn', `${title}: ${text}`)
/** ConstraintCreationMode: Driving, or Reference (Sketcher_ToggleDrivingConstraint with nothing selected). */
let creationMode: 'Driving' | 'Reference' = 'Driving'
export const constraintCreationMode = () => creationMode
/** "%.8g": the value as the command writes it into the Python call. */
const g8 = (v: number) => Number(v.toPrecision(8))
/** isPointOrSegmentFixed: external geometry, the axes, the root, or blocked geometry. */
function isFixed(g: number) {
  if (g === GEO_UNDEF) return false
  if (g < 0) return true
  return S.getConstraints().some((c) => c.type === 'Block' && c.first === g)
}
const bothFixed = (a: number, b: number) => isFixed(a) && (b === GEO_UNDEF || isFixed(b))
function noFixed() { warn('Wrong selection', 'Cannot add a constraint between two fixed geometries. Fixed geometries include external geometry, blocked geometry, and special points such as B-spline knot points.') }

/** finishTransactionAndUpdate. */
function finish() { S.commitCommand(); S.clearSelection(); S.solve() }
/** finishDatumConstraint: the label placed, then the datum dialog for a driving dimension. */
let datumDialog: ((id: number, onDone: (accepted: boolean) => void) => void) | null = null
export function onDatumDialog(f: typeof datumDialog) { datumDialog = f }
function finishDatum(reference: boolean) {
  if (reference) { const cs = S.getConstraints(); S.setConstraint(cs.length - 1, { ...cs[cs.length - 1], driving: false }) }
  const cs = S.getConstraints(), i = cs.length - 1, c = { ...cs[i] }
  if (c.type === 'Radius' || c.type === 'Diameter') { if (SK.isCircle(geo(c.first))) c.labelPosition = (15 * Math.PI) / 180 } // RadiusDiameterConstraintDisplayBaseAngle
  S.setConstraint(i, c)
  const pos = c.type === 'Angle' ? angularLabelPosition(c) : linearLabelPosition(c)
  if (pos) S.moveConstraint(i, pos)
  S.solve()
  // ShowDialogOnDistanceConstraint (on): the dialog takes the transaction; without it, the command commits here
  if (!reference && datumDialog) datumDialog(i, () => { S.clearSelection() })
  else { S.commitCommand(); S.clearSelection() }
}
/** LinearDatumLabelPlacement::computeLabelPosition. */
function linearLabelPosition(c: Constraint): XY | null {
  if (c.type !== 'DistanceX' && c.type !== 'DistanceY' && c.type !== 'Distance') return null
  let a: XY, b: XY
  if (c.secondPos !== NONE) { a = S.getPoint(c.first, c.firstPos)!; b = S.getPoint(c.second, c.secondPos)! }
  else if (c.firstPos !== NONE && c.second === GEO_UNDEF) { a = [0, 0]; b = S.getPoint(c.first, c.firstPos)! }
  else if (c.type === 'Distance' && c.second === GEO_UNDEF && c.first >= 0) { const g = geo(c.first); if (!SK.isLine(g)) return null; a = g.start; b = g.end }
  else return null
  const eps = 1e-7
  let dir: XY
  if (c.type === 'DistanceX') { if (b[0] < a[0] - eps) [a, b] = [b, a]; dir = [0, -1] }
  else if (c.type === 'DistanceY') { if (b[1] < a[1] - eps) [a, b] = [b, a]; dir = b[0] > a[0] + eps ? [1, 0] : b[0] < a[0] - eps ? [-1, 0] : [1, 0] }
  else {
    if (b[1] < a[1] - eps || (Math.abs(b[1] - a[1]) <= eps && b[0] < a[0] - eps)) [a, b] = [b, a]
    const span: XY = [b[0] - a[0], b[1] - a[1]], l = Math.hypot(span[0], span[1])
    if (l <= eps) return null
    dir = span[0] >= 0 ? [-span[1] / l, span[0] / l] : [span[1] / l, -span[0] / l]
  }
  const span: XY = [b[0] - a[0], b[1] - a[1]], k = c.labelDistance + 0.5 * Math.abs(span[0] * dir[0] + span[1] * dir[1])
  return [(a[0] + b[0]) / 2 + dir[0] * k, (a[1] + b[1]) / 2 + dir[1] * k]
}
/** AngularDatumLabelPlacement::computeLabelPosition (between two lines meeting outside both, or a line and an axis). */
function angularLabelPosition(c: Constraint): XY | null {
  if (c.second === GEO_UNDEF) {
    const g = geo(c.first)
    if (!SK.isArc(g)) return null
    const m = (g.start_angle + g.end_angle) / 2
    return [g.center[0] + Math.cos(m) * (g.radius + c.labelDistance), g.center[1] + Math.sin(m) * (g.radius + c.labelDistance)]
  }
  return null
}

// ── the commands ─────────────────────────────────────────────────────────────────────────────────────────────────
type Cmd = { name: string; sequences: string[][]; run(sel: SelId[], fromTool?: number): void; hints?: string[] }
const lineOK = (g: number) => g < 0 ? g === H_AXIS || g === V_AXIS : SK.isLine(geo(g))

/** canHorVerBlock. */
function canHorVerBlock(g: number) {
  for (const c of S.getConstraints()) {
    if (c.first !== g || c.firstPos !== NONE) continue
    if (c.type === 'Horizontal') { warn('Double constraint', 'The selected edge already has a horizontal constraint!'); return false }
    if (c.type === 'Vertical') { warn('Impossible constraint', 'The selected edge already has a vertical constraint!'); return false }
    if (c.type === 'Block') { warn('Impossible constraint', 'The selected edge already has a block constraint!'); return false }
  }
  return true
}
/** horVerActivated: edges become horizontal (or vertical, or whichever they are closer to), else point pairs line up. */
function horVer(type: 'Horizontal' | 'Vertical' | 'HorVer', sel: SelId[]) {
  const edges: number[] = [], points: SelId[] = []
  let fixedPoints = 0
  for (const s of sel) {
    if (isEdge(s) && s.geoId >= 0) {
      if (!SK.isLine(geo(s.geoId))) { warn('Impossible constraint', 'The selected edge is not a line segment.'); return }
      if (canHorVerBlock(s.geoId)) edges.push(s.geoId)
    } else if (isVertex(s)) { if (isFixed(s.geoId)) fixedPoints++; points.push(s) }
  }
  if (!edges.length && points.length < 2) { warn('Impossible constraint', 'The selected items cannot be constrained horizontally or vertically!'); return }
  const closer = (a: XY, b: XY): 'Horizontal' | 'Vertical' => { const an = Math.atan2(b[1] - a[1], b[0] - a[0]); return Math.abs(Math.sin(an)) < Math.abs(Math.cos(an)) ? 'Horizontal' : 'Vertical' }
  if (edges.length) {
    S.openCommand(type === 'Horizontal' ? 'Add horizontal constraint' : type === 'Vertical' ? 'Add vertical constraint' : 'Add horizontal/vertical constraint')
    for (const g of edges) { const l = geo(g) as { start: XY; end: XY }; S.addConstraint(constraint(type === 'HorVer' ? closer(l.start, l.end) : type, g)) }
  } else if (fixedPoints <= 1) {
    S.openCommand(type === 'Horizontal' ? 'Add horizontal alignment' : type === 'Vertical' ? 'Add vertical alignment' : 'Add horizontal/vertical alignment')
    for (let i = 0; i + 1 < points.length; i++) {
      const a = points[i], b = points[i + 1]
      S.addConstraint(constraint(type === 'HorVer' ? closer(P(a), P(b)) : type, a.geoId, a.pos, b.geoId, b.pos))
    }
  } else { warn('Impossible constraint', 'There are more than one fixed points selected. Select a maximum of one fixed point!'); return }
  finish()
}

const COMMANDS: Record<string, Cmd> = {
  Sketcher_ConstrainHorizontal: { name: 'Horizontal', sequences: [['Edge'], ['VertexOrRoot', 'VertexOrRoot']], run: (s) => horVer('Horizontal', s) },
  Sketcher_ConstrainVertical: { name: 'Vertical', sequences: [['Edge'], ['VertexOrRoot', 'VertexOrRoot']], run: (s) => horVer('Vertical', s) },
  Sketcher_ConstrainHorVer: { name: 'HorVer', sequences: [['Edge'], ['VertexOrRoot', 'VertexOrRoot']], run: (s) => horVer('HorVer', s) },
  Sketcher_ConstrainLock: {
    name: 'Lock', sequences: [['Vertex']],
    run(sel) {
      if (sel.some((s, i) => (i < sel.length - 1 && (isEdge(s) || (s.geoId < 0 && s.geoId >= V_AXIS))) || (i === sel.length - 1 && isEdge(s)))) {
        warn('Wrong selection', 'Select one vertex from the sketch other than the origin.'); S.clearSelection(); return
      }
      if (sel.length === 1) {
        const [s] = sel, p = P(s)
        S.openCommand("Add 'Lock' constraint")
        S.addConstraint([constraint('DistanceX', s.geoId, s.pos, GEO_UNDEF, NONE, GEO_UNDEF, NONE, g8(p[0])), constraint('DistanceY', s.geoId, s.pos, GEO_UNDEF, NONE, GEO_UNDEF, NONE, g8(p[1]))])
        if (isFixed(s.geoId) || creationMode === 'Reference') { const cs = S.getConstraints(); for (const k of [cs.length - 2, cs.length - 1]) S.setConstraint(k, { ...cs[k], driving: false }) }
      } else {
        const ref = sel[sel.length - 1], pr = P(ref)
        S.openCommand("Add relative 'Lock' constraint")
        for (const s of sel.slice(0, -1)) {
          const p = P(s)
          S.addConstraint([constraint('DistanceX', s.geoId, s.pos, ref.geoId, ref.pos, GEO_UNDEF, NONE, g8(pr[0] - p[0])), constraint('DistanceY', s.geoId, s.pos, ref.geoId, ref.pos, GEO_UNDEF, NONE, g8(pr[1] - p[1]))])
          if ((isFixed(ref.geoId) && isFixed(s.geoId)) || creationMode === 'Reference') { const cs = S.getConstraints(); for (const k of [cs.length - 2, cs.length - 1]) S.setConstraint(k, { ...cs[k], driving: false }) }
        }
      }
      finish()
    },
  },
  Sketcher_ConstrainBlock: {
    name: 'Block', sequences: [['Edge']],
    run(sel) {
      const r = S.getResult()
      if (r && (r.status === 'failed' || r.conflicting.length || r.redundant.length)) { warn('Wrong solver status', 'A block constraint cannot be added if the sketch is unsolved or there are redundant and conflicting constraints.'); return }
      const ids: number[] = []
      for (const s of sel) {
        if (isVertex(s) || s.geoId < 0) { warn('Wrong selection', 'Select one edge from the sketch.'); S.clearSelection(); return }
        if (S.getConstraints().some((c) => c.type === 'Block' && c.first === s.geoId)) { warn('Double constraint', 'The selected edge already has a block constraint!'); return }
        ids.push(s.geoId)
      }
      for (const g of ids) { S.openCommand('Add Block constraint'); S.addConstraint(constraint('Block', g)); S.commitCommand(); S.solve() }
      S.clearSelection()
    },
  },
  Sketcher_ConstrainCoincidentUnified: { name: 'Coincident', sequences: [['Vertex', 'EdgeOrAxis'], ['Root', 'Edge'], ['Edge', 'VertexOrRoot'], ['EdgeOrAxis', 'Vertex'], ['VertexOrRoot', 'VertexOrRoot'], ['Edge', 'Edge']], run: (s) => coincident(s, 'both') },
  Sketcher_ConstrainCoincident: { name: 'Coincident', sequences: [['VertexOrRoot', 'VertexOrRoot'], ['Edge', 'Edge']], run: (s) => coincident(s, 'coincident') },
  Sketcher_ConstrainPointOnObject: { name: 'PointOnObject', sequences: [['Vertex', 'EdgeOrAxis'], ['Root', 'Edge'], ['Edge', 'VertexOrRoot'], ['EdgeOrAxis', 'Vertex']], run: (s) => coincident(s, 'pointOnObject') },
  Sketcher_ConstrainDistance: { name: 'Distance', sequences: [['VertexOrRoot', 'VertexOrRoot'], ['Edge'], ['Vertex', 'EdgeOrAxis'], ['Root', 'Edge'], ['Edge', 'Edge']], run: distance },
  Sketcher_ConstrainDistanceX: { name: 'DistanceX', sequences: [['VertexOrRoot', 'VertexOrRoot'], ['Edge']], run: (s) => coordinateDistance(s, true) },
  Sketcher_ConstrainDistanceY: { name: 'DistanceY', sequences: [['VertexOrRoot', 'VertexOrRoot'], ['Edge']], run: (s) => coordinateDistance(s, false) },
  Sketcher_ConstrainParallel: {
    name: 'Parallel', sequences: [['Edge', 'EdgeOrAxis'], ['EdgeOrAxis', 'Edge']],
    run(sel) {
      const ids: number[] = []
      let ext = false
      for (const s of sel) {
        if (!isEdge(s)) continue
        if (isFixed(s.geoId)) { if (ext) { noFixed(); return } ext = true }
        if (!lineOK(s.geoId)) { warn('Wrong selection', 'One selected edge is not a valid line.'); return }
        ids.push(s.geoId)
      }
      if (ids.length < 2) { warn('Wrong selection', 'Select at least two lines from the sketch.'); return }
      S.openCommand('Add parallel constraint')
      for (let i = 0; i + 1 < ids.length; i++) S.addConstraint(constraint('Parallel', ids[i], NONE, ids[i + 1]))
      finish()
    },
  },
  Sketcher_ConstrainPerpendicular: { name: 'Perpendicular', sequences: [['Edge', 'EdgeOrAxis'], ['EdgeOrAxis', 'Edge'], ['VertexOrRoot', 'Edge', 'EdgeOrAxis'], ['Vertex', 'Vertex'], ['Vertex', 'Edge'], ['Edge', 'Vertex']], run: (s) => perpTangent('Perpendicular', s) },
  Sketcher_ConstrainTangent: { name: 'Tangent', sequences: [['Edge', 'EdgeOrAxis'], ['EdgeOrAxis', 'Edge'], ['Vertex', 'Vertex'], ['Vertex', 'Edge'], ['Edge', 'Vertex']], run: (s) => perpTangent('Tangent', s) },
  Sketcher_ConstrainEqual: {
    name: 'Equal', sequences: [['Edge', 'Edge']],
    run(sel) {
      const ids: number[] = []
      let lines = 0, circles = 0, ext = false
      for (const s of sel) {
        if (!isEdge(s) || s.geoId < 0) continue
        if (isFixed(s.geoId)) { if (ext) { noFixed(); return } ext = true }
        const g = geo(s.geoId)
        if (SK.isLine(g)) lines++; else if (SK.isCircular(g)) circles++; else { warn('Wrong selection', 'Select two or more edges of similar type.'); return }
        ids.push(s.geoId)
      }
      if (ids.length < 2) { warn('Wrong selection', 'Select two or more edges of similar type.'); return }
      if (lines && circles) { warn('Wrong selection', 'Select two or more edges of similar type.'); return }
      S.openCommand('Add equality constraint')
      for (let i = 0; i + 1 < ids.length; i++) S.addConstraint(constraint('Equal', ids[i], NONE, ids[i + 1]))
      finish()
    },
  },
  Sketcher_ConstrainSymmetric: {
    name: 'Symmetric', sequences: [['Vertex', 'Vertex', 'EdgeOrAxis'], ['Vertex', 'Vertex', 'VertexOrRoot'], ['Edge', 'VertexOrRoot']],
    run(sel) {
      if (sel.length === 2 && isEdge(sel[0]) && SK.isLine(geo(sel[0].geoId)) && isVertex(sel[1])) {
        const g = sel[0].geoId
        S.openCommand('Add symmetric constraint')
        S.addConstraint(constraint('Symmetric', g, START, g, END, sel[1].geoId, sel[1].pos))
        finish(); return
      }
      if (sel.length !== 3) { warn('Wrong selection', 'Select two points and a symmetry line, two points and a symmetry point or a line and a symmetry point from the sketch.'); return }
      let [a, b, c] = sel
      if (isEdge(a)) [a, c] = [c, a]
      if (isEdge(b)) [b, c] = [c, b]
      if (!isVertex(a) || !isVertex(b)) { warn('Wrong selection', 'Select two points and a symmetry line, two points and a symmetry point or a line and a symmetry point from the sketch.'); return }
      if (a.geoId === b.geoId && a.geoId === c.geoId) { warn('Wrong selection', 'Cannot add a symmetry constraint between a line and its end points.'); return }
      S.openCommand('Add symmetric constraint')
      if (isEdge(c)) S.addConstraint(constraint('Symmetric', a.geoId, a.pos, b.geoId, b.pos, c.geoId))
      else S.addConstraint(constraint('Symmetric', a.geoId, a.pos, b.geoId, b.pos, c.geoId, c.pos))
      finish()
    },
  },
  Sketcher_ConstrainRadius: { name: 'Radius', sequences: [['Edge']], run: (s) => radial(s, 'Radius') },
  Sketcher_ConstrainDiameter: { name: 'Diameter', sequences: [['Edge']], run: (s) => radial(s, 'Diameter') },
  Sketcher_ConstrainRadiam: { name: 'Radiam', sequences: [['Edge']], run: (s) => radial(s, 'Radiam') },
  Sketcher_ConstrainAngle: { name: 'Angle', sequences: [['Edge', 'EdgeOrAxis'], ['EdgeOrAxis', 'Edge']], run: angle },
  Sketcher_Dimension: { name: 'Dimension', sequences: [['Edge'], ['VertexOrRoot', 'VertexOrRoot'], ['Vertex', 'Edge'], ['Edge', 'Vertex'], ['Edge', 'Edge']], run: dimension },
}

/** CmdSketcherConstrainCoincidentUnified: one point and curves (or one curve and points) go onto each other; points
 *  together; circles and arcs concentric. */
function coincident(sel: SelId[], mode: 'both' | 'coincident' | 'pointOnObject') {
  const points = sel.filter(isVertex), curves = sel.filter(isEdge)
  if (mode !== 'coincident' && ((points.length === 1 && curves.length) || (points.length && curves.length === 1))) {
    S.openCommand('Add point on object constraint')
    let n = 0
    for (const p of points) for (const c of curves) {
      if (bothFixed(p.geoId, c.geoId)) { noFixed(); continue }
      if (p.geoId === c.geoId) continue
      n++
      S.addConstraint(constraint('PointOnObject', p.geoId, p.pos, c.geoId))
    }
    if (n) finish()
    else { S.abortCommand(); warn('Wrong selection', 'None of the selected points were constrained onto the respective curves, because they are part of the same element, they are both external geometry, or the edge is not eligible.') }
    return
  }
  if (mode !== 'pointOnObject' && ((points.length && !curves.length) || (!points.length && curves.length))) {
    if (curves.some((c) => !SK.isCircular(geo(c.geoId)))) { warn('Wrong selection', 'Select two or more vertices from the sketch for a coincident constraint, or two or more circles, ellipses, arcs or arcs of ellipse for a concentric constraint.'); return }
    const use = curves.length ? curves.map((c) => ({ geoId: c.geoId, pos: MID as PointPos })) : points
    const [first] = use
    S.openCommand('Add coincident constraint')
    let added = false
    for (const s of use.slice(1)) {
      if (bothFixed(first.geoId, s.geoId)) { noFixed(); S.abortCommand(); return }
      if (first.geoId === s.geoId && first.pos === s.pos) continue
      if (SK.coincidentPoints(S.getConstraints(), first.geoId, first.pos).get(s.geoId) === s.pos) continue // already coincident
      S.addConstraint(constraint('Coincident', first.geoId, first.pos, s.geoId, s.pos))
      added = true
    }
    if (added) finish()
    else { S.abortCommand(); warn('Wrong selection', 'The selected points are already coincident.') }
    return
  }
  warn('Wrong selection', mode === 'coincident' ? 'Select either several points, or several conics for concentricity.'
    : mode === 'pointOnObject' ? 'Select either one point and several curves, or one curve and several points'
      : 'Select either one point and several curves or one curve and several points for pointOnObject, or several points for coincidence, or several conics for concentricity.')
}
/** CmdSketcherConstrainDistance::activated. */
function distance(sel: SelId[]) {
  if (!sel.length || sel.length > 2) { warn('Wrong selection', 'Select exactly one line or one point and one line or two points or two circles from the sketch.'); return }
  let [a, b] = [sel[0], sel[1] ?? { geoId: GEO_UNDEF, pos: NONE as PointPos }]
  const fixed = bothFixed(a.geoId, b.geoId)
  if (isVertex(a) && isAxis(b)) [a, b] = [b, a]
  if ((isVertex(a) || isAxis(a)) && isVertex(b)) {
    const p2 = P(b)
    if (a.geoId === H_AXIS && a.pos === NONE) { S.openCommand('Add distance from horizontal axis constraint'); S.addConstraint(constraint('DistanceY', a.geoId, START, b.geoId, b.pos, GEO_UNDEF, NONE, g8(p2[1]))) }
    else if (a.geoId === V_AXIS && a.pos === NONE) { S.openCommand('Add distance from vertical axis constraint'); S.addConstraint(constraint('DistanceX', a.geoId, START, b.geoId, b.pos, GEO_UNDEF, NONE, g8(p2[0]))) }
    else { const p1 = P(a); S.openCommand('Add point to point distance constraint'); S.addConstraint(constraint('Distance', a.geoId, a.pos, b.geoId, b.pos, GEO_UNDEF, NONE, g8(Math.hypot(p2[0] - p1[0], p2[1] - p1[1])))) }
    finishDatum(fixed || creationMode === 'Reference'); return
  }
  if ((isVertex(a) && isEdge(b)) || (isEdge(a) && isVertex(b))) {
    if (isVertex(b)) [a, b] = [b, a]
    const p = P(a), g = b.geoId < 0 ? (b.geoId === H_AXIS ? { start: [0, 0] as XY, end: [1, 0] as XY } : { start: [0, 0] as XY, end: [0, 1] as XY }) : geo(b.geoId)
    if ('start' in g) {
      S.openCommand('Add point to line distance constraint')
      S.addConstraint(constraint('Distance', a.geoId, a.pos, b.geoId, NONE, GEO_UNDEF, NONE, g8(SK.distToLine(p, g.start, g.end))))
      finishDatum(fixed || creationMode === 'Reference'); return
    }
    if (SK.isCircular(g)) {
      const c = g as { center: XY; radius: number }
      S.openCommand('Add point to circle distance constraint')
      S.addConstraint(constraint('Distance', a.geoId, a.pos, b.geoId, NONE, GEO_UNDEF, NONE, g8(Math.abs(Math.hypot(c.center[0] - p[0], c.center[1] - p[1]) - c.radius))))
      finishDatum(fixed || creationMode === 'Reference'); return
    }
  }
  if (isEdge(a) && isEdge(b) && a.geoId >= 0 && b.geoId >= 0) {
    const g1 = geo(a.geoId), g2 = geo(b.geoId)
    if (SK.isCircular(g1) && SK.isCircular(g2)) {
      S.openCommand('Add circle to circle distance constraint')
      S.addConstraint(constraint('Distance', a.geoId, NONE, b.geoId, NONE, GEO_UNDEF, NONE, g8(SK.measure(S.getGeometry(), constraint('Distance', a.geoId, NONE, b.geoId)))))
      finishDatum(fixed || creationMode === 'Reference'); return
    }
    if ((SK.isCircular(g1) && SK.isLine(g2)) || (SK.isLine(g1) && SK.isCircular(g2))) {
      if (SK.isLine(g1)) [a, b] = [b, a]
      S.openCommand('Add circle to line distance constraint')
      S.addConstraint(constraint('Distance', a.geoId, NONE, b.geoId, NONE, GEO_UNDEF, NONE, g8(SK.measure(S.getGeometry(), constraint('Distance', a.geoId, NONE, b.geoId)))))
      finishDatum(fixed || creationMode === 'Reference'); return
    }
    warn('Wrong selection', 'Select exactly one line or one point and one line or two points or two circles from the sketch.'); return
  }
  if (isEdge(a) && b.geoId === GEO_UNDEF) {
    if (a.geoId < 0) return
    const g = geo(a.geoId)
    if (SK.isLine(g)) {
      S.openCommand('Add length constraint')
      S.addConstraint(constraint('Distance', a.geoId, NONE, GEO_UNDEF, NONE, GEO_UNDEF, NONE, g8(Math.hypot(g.end[0] - g.start[0], g.end[1] - g.start[1]))))
      finishDatum(isFixed(a.geoId) || creationMode === 'Reference'); return
    }
    if (SK.isArc(g)) {
      S.openCommand('Add length constraint')
      S.addConstraint(constraint('Distance', a.geoId, NONE, GEO_UNDEF, NONE, GEO_UNDEF, NONE, g8((g.end_angle - g.start_angle) * g.radius)))
      finishDatum(isFixed(a.geoId) || creationMode === 'Reference'); return
    }
  }
  warn('Wrong selection', 'Select exactly one line or one point and one line or two points or two circles from the sketch.')
}
/** activateCoordinateDistanceConstraint: DistanceX and DistanceY. */
function coordinateDistance(sel: SelId[], horizontal: boolean) {
  if (!sel.length || sel.length > 2) return
  let [a, b] = [sel[0], sel[1] ?? { geoId: GEO_UNDEF, pos: NONE as PointPos }]
  let fixed = bothFixed(a.geoId, b.geoId)
  if (b.geoId === H_AXIS || b.geoId === V_AXIS) [a, b] = [b, a]
  if (a.geoId === (horizontal ? H_AXIS : V_AXIS) && a.pos === NONE) a = { geoId: GEO_UNDEF, pos: NONE }
  else if (a.geoId === (horizontal ? V_AXIS : H_AXIS) && a.pos === NONE) a = { geoId: H_AXIS, pos: START }
  if (isEdge(a) && b.geoId === GEO_UNDEF) {
    if (a.geoId < 0) return
    fixed = isFixed(a.geoId)
    if (SK.isLine(geo(a.geoId))) { b = { geoId: a.geoId, pos: END }; a = { geoId: a.geoId, pos: START } }
  }
  const T = horizontal ? 'DistanceX' : 'DistanceY', k = horizontal ? 0 : 1
  if (isVertex(a) && isVertex(b)) {
    let p1 = P(a), p2 = P(b), v = p2[k] - p1[k]
    if (v < -1e-7) { [a, b] = [b, a]; [p1, p2] = [p2, p1]; v = -v }
    S.openCommand(horizontal ? 'Add point to point horizontal distance constraint' : 'Add point to point vertical distance constraint')
    S.addConstraint(constraint(T, a.geoId, a.pos, b.geoId, b.pos, GEO_UNDEF, NONE, g8(v)))
    finishDatum(fixed || creationMode === 'Reference'); return
  }
  if (isVertex(a) && b.geoId === GEO_UNDEF) {
    if (a.geoId < 0 && a.geoId >= V_AXIS) return
    S.openCommand(horizontal ? 'Add fixed x-coordinate constraint' : 'Add fixed y-coordinate constraint')
    S.addConstraint(constraint(T, a.geoId, a.pos, GEO_UNDEF, NONE, GEO_UNDEF, NONE, g8(P(a)[k])))
    finishDatum(isFixed(a.geoId) || creationMode === 'Reference')
  }
}
/** CmdSketcherConstrainPerpendicular / Tangent::activated, for lines, circles and arcs. */
function perpTangent(T: 'Perpendicular' | 'Tangent', sel: SelId[]) {
  if (sel.length !== 2 && sel.length !== 3) { warn('Wrong selection', `Select some geometry from the sketch.`); return }
  let [a, b] = sel
  if (bothFixed(a.geoId, b.geoId)) { noFixed(); return }
  if (sel.length === 3) {
    let c = sel[2]
    if (isVertex(a)) [a, b] = [b, a]
    if (isVertex(b)) [b, c] = [c, b]
    if (isEdge(a) && isEdge(b) && isVertex(c)) {
      S.openCommand(`Add ${T === 'Tangent' ? 'tangent' : 'perpendicular'} constraint`)
      S.addConstraint([constraint('PointOnObject', c.geoId, c.pos, a.geoId), constraint('PointOnObject', c.geoId, c.pos, b.geoId), constraint(T, a.geoId, NONE, b.geoId, NONE, c.geoId, c.pos)])
      finish()
    }
    return
  }
  const simple = (s: SelId) => {
    const g = geo(s.geoId)
    // isSimpleVertex: a point of its own, or a curve's end that touches nothing else
    if (g?.type === 'Point') return true
    if (s.pos === MID) return true
    return SK.coincidentPoints(S.getConstraints(), s.geoId, s.pos).size === 0
  }
  if (isVertex(a) && isVertex(b)) {
    if (simple(a) || simple(b)) { warn('Wrong selection', `Cannot add a ${T === 'Tangent' ? 'tangency' : 'perpendicularity'} constraint at an unconnected point!`); return }
    S.openCommand(`Add ${T === 'Tangent' ? 'tangent' : 'perpendicular'} constraint`)
    // the coincidence between the two points is folded into the endpoint constraint (substituteConstraintCombinations)
    const cs = S.getConstraints(), k = cs.findIndex((c) => c.type === 'Coincident' && ((c.first === a.geoId && c.firstPos === a.pos && c.second === b.geoId && c.secondPos === b.pos) || (c.first === b.geoId && c.firstPos === b.pos && c.second === a.geoId && c.secondPos === a.pos)))
    if (k >= 0) S.delConstraints([k])
    S.addConstraint(constraint(T, a.geoId, a.pos, b.geoId, b.pos))
    finish(); return
  }
  if ((isVertex(a) && isEdge(b)) || (isEdge(a) && isVertex(b))) {
    if (isVertex(b)) [a, b] = [b, a]
    if (simple(a)) { warn('Wrong selection', `Cannot add a ${T === 'Tangent' ? 'tangency' : 'perpendicularity'} constraint at an unconnected point!`); return }
    S.openCommand(`Add ${T === 'Tangent' ? 'tangent' : 'perpendicularity'} constraint`)
    S.addConstraint(constraint(T, a.geoId, a.pos, b.geoId))
    finish(); return
  }
  if (isEdge(a) && isEdge(b)) {
    const g1 = a.geoId < 0 ? { type: 'LineSegment' } : geo(a.geoId), g2 = b.geoId < 0 ? { type: 'LineSegment' } : geo(b.geoId)
    if (T === 'Perpendicular') {
      if (g1.type !== 'LineSegment' && g2.type !== 'LineSegment') { warn('Wrong selection', 'One of the selected edges should be a line.'); return }
      if (g1.type === 'LineSegment') [a, b] = [b, a]
    } else if (g1.type === 'LineSegment' && g2.type === 'LineSegment') {
      // two lines: collinear (Tangent), as FreeCAD's tangent between lines is
    }
    S.openCommand(`Add ${T === 'Tangent' ? 'tangent' : 'perpendicular'} constraint`)
    S.addConstraint(constraint(T, a.geoId, NONE, b.geoId))
    finish()
  }
}
/** activateRadialDimension: radius, diameter, or (Radiam) a diameter for a circle and a radius for an arc. */
function radial(sel: SelId[], kind: 'Radius' | 'Diameter' | 'Radiam') {
  const items = sel.filter((s) => isEdge(s) && s.geoId >= 0 && SK.isCircular(geo(s.geoId)))
  if (!items.length || items.length !== sel.length) { warn('Wrong selection', 'Select one or more arcs or circles from the sketch.'); return }
  S.openCommand(kind === 'Radius' ? 'Add radius constraint' : kind === 'Diameter' ? 'Add diameter constraint' : 'Add radiam constraint')
  for (const s of items) {
    const g = geo(s.geoId) as { radius: number }
    const t = kind === 'Radiam' ? (SK.isCircle(geo(s.geoId)) ? 'Diameter' : 'Radius') : kind
    S.addConstraint(constraint(t, s.geoId, NONE, GEO_UNDEF, NONE, GEO_UNDEF, NONE, g8(t === 'Diameter' ? 2 * g.radius : g.radius)))
  }
  finishDatum(items.every((s) => isFixed(s.geoId)) || creationMode === 'Reference')
}
/** CmdSketcherConstrainAngle::activated: a line's angle, an arc's, or two lines' (calculateAngle). */
function angle(sel: SelId[]) {
  if (!sel.length || sel.length > 3) { warn('Wrong selection', 'Select one or two lines from the sketch. Or select two edges and a point.'); return }
  let [a, b] = [sel[0], sel[1] ?? { geoId: GEO_UNDEF, pos: NONE as PointPos }]
  if (isVertex(a) && isEdge(b)) [a, b] = [b, a]
  if (isEdge(b)) {
    const L = (g: number) => (g === H_AXIS ? { start: [0, 0] as XY, end: [1, 0] as XY } : g === V_AXIS ? { start: [0, 0] as XY, end: [0, 1] as XY } : geo(g))
    const l1 = L(a.geoId), l2 = L(b.geoId)
    if (!('start' in l1) || !('start' in l2)) return
    const p1 = [l1.start, l1.end], p2 = [l2.start, l2.end]
    const d1: XY = [l1.end[0] - l1.start[0], l1.end[1] - l1.start[1]], d2: XY = [l2.end[0] - l2.start[0], l2.end[1] - l2.start[1]]
    const det = d1[0] * d2[1] - d1[1] * d2[0]
    let pos1: PointPos, pos2: PointPos
    const d2s = (u: XY, v: XY) => (u[0] - v[0]) ** 2 + (u[1] - v[1]) ** 2
    if (Math.abs(det) > 1e-12) {
      const t = ((l2.start[0] - l1.start[0]) * d2[1] - (l2.start[1] - l1.start[1]) * d2[0]) / det
      const s: XY = [l1.start[0] + t * d1[0], l1.start[1] + t * d1[1]]
      pos1 = d2s(s, p1[0]) < d2s(s, p1[1]) ? START : END
      pos2 = d2s(s, p2[0]) < d2s(s, p2[1]) ? START : END
    } else {
      let best = Infinity; pos1 = START; pos2 = START
      for (let i = 0; i < 2; i++) for (let j = 0; j < 2; j++) { const d = d2s(p2[j], p1[i]); if (d < best) { best = d; pos1 = i ? END : START; pos2 = j ? END : START } }
    }
    const dir1 = d1.map((v) => (pos1 === START ? v : -v)) as XY, dir2 = d2.map((v) => (pos2 === START ? v : -v)) as XY
    let act = Math.atan2(dir1[0] * dir2[1] - dir1[1] * dir2[0], dir1[1] * dir2[1] + dir1[0] * dir2[0])
    if (Math.abs(dir1[0] * dir2[1] - dir1[1] * dir2[0]) < 1e-9 * Math.hypot(...dir1) * Math.hypot(...dir2)) { warn('Parallel lines', 'An angle constraint cannot be set for two parallel lines.'); return }
    let g1 = a.geoId, g2 = b.geoId
    if (act < 0) { act = -act; [g1, g2] = [g2, g1]; [pos1, pos2] = [pos2, pos1] }
    S.openCommand('Add angle constraint')
    S.addConstraint(constraint('Angle', g1, pos1, g2, pos2, GEO_UNDEF, NONE, g8(act)))
    finishDatum(bothFixed(g1, g2) || creationMode === 'Reference'); return
  }
  if (isEdge(a)) {
    if (a.geoId < 0) return
    const g = geo(a.geoId)
    if (SK.isLine(g)) { S.openCommand('Add angle constraint'); S.addConstraint(constraint('Angle', a.geoId, NONE, GEO_UNDEF, NONE, GEO_UNDEF, NONE, g8(Math.atan2(g.end[1] - g.start[1], g.end[0] - g.start[0])))); finishDatum(creationMode === 'Reference'); return }
    if (SK.isArc(g)) { S.openCommand('Add angle constraint'); S.addConstraint(constraint('Angle', a.geoId, NONE, GEO_UNDEF, NONE, GEO_UNDEF, NONE, g8(g.end_angle - g.start_angle))); finishDatum(creationMode === 'Reference') }
  }
}
/** Sketcher_Dimension with a selection: the dimension the selection calls for (a line's length, a circle's diameter or
 *  an arc's radius, two points' distance, a point and a line, two lines' angle). */
function dimension(sel: SelId[]) {
  if (sel.length === 1 && isEdge(sel[0]) && sel[0].geoId >= 0 && SK.isCircular(geo(sel[0].geoId))) return radial(sel, 'Radiam')
  if (sel.length === 2 && isEdge(sel[0]) && isEdge(sel[1]) && lineOK(sel[0].geoId) && lineOK(sel[1].geoId)) return angle(sel)
  return distance(sel)
}

/** Sketcher_ToggleDrivingConstraint: the selected dimensions between driving and reference; with none selected, the
 *  creation mode of new ones. */
export function toggleDriving() {
  const ids = [...S.selectedConstraints()].filter((i) => SK.isDimensional(S.getConstraints()[i]))
  if (!ids.length) { creationMode = creationMode === 'Driving' ? 'Reference' : 'Driving'; return }
  S.openCommand('Toggle constraint to driving/reference')
  for (const i of ids) { const c = S.getConstraints()[i]; S.setConstraint(i, { ...c, driving: !c.driving, ...(c.driving ? {} : { value: SK.measure(S.getGeometry(), c) }) }) }
  finish()
}
/** Sketcher_ToggleActiveConstraint. */
export function toggleActive() {
  const ids = [...S.selectedConstraints()]
  if (!ids.length) return
  S.openCommand('Activate/Deactivate constraints')
  for (const i of ids) { const c = S.getConstraints()[i]; S.setConstraint(i, { ...c, active: !c.active }) }
  finish()
}

/** Runs a constraint command: on the selection, or (none) with the selection tool. */
export function runConstraint(name: string) {
  const cmd = COMMANDS[name]
  if (!cmd) return
  const sel = selection()
  if (sel.length) { cmd.run(sel); return }
  S.activateHandler(new GenConstraintHandler(name, cmd))
}
export const isConstraintCommand = (name: string) => name in COMMANDS

// ── DrawSketchHandlerGenConstraint ───────────────────────────────────────────────────────────────────────────────
const CONSTRAINT_CURSOR: Record<string, string> = {
  Horizontal: 'Constraint_Horizontal', Vertical: 'Constraint_Vertical', HorVer: 'Constraint_HorVer', Lock: 'Constraint_Lock', Block: 'Constraint_Block',
  Coincident: 'Constraint_PointOnPoint', PointOnObject: 'Constraint_PointOnObject', Distance: 'Constraint_Length', DistanceX: 'Constraint_HorizontalDistance',
  DistanceY: 'Constraint_VerticalDistance', Parallel: 'Constraint_Parallel', Perpendicular: 'Constraint_Perpendicular', Tangent: 'Constraint_Tangent',
  Equal: 'Constraint_EqualLength', Symmetric: 'Constraint_Symmetric', Radius: 'Constraint_Radius', Diameter: 'Constraint_Diameter', Radiam: 'Constraint_Radiam',
  Angle: 'Constraint_InternalAngle', Dimension: 'Constraint_Dimension',
}
/** The kind of element a click picked (SelType). */
function selType(s: SelId): string[] {
  if (isRoot(s)) return ['Root', 'VertexOrRoot']
  if (isVertex(s)) return ['Vertex', 'VertexOrRoot']
  if (isAxis(s)) return ['EdgeOrAxis', s.geoId === H_AXIS ? 'HAxis' : 'VAxis']
  if (isEdge(s) && s.geoId >= 0) return ['Edge', 'EdgeOrAxis']
  return []
}
class GenConstraintHandler implements S.Handler {
  readonly toolName = 'DSH_GenConstraint'
  private seq: SelId[] = []
  constructor(private cmdName: string, private cmd: Cmd) {}
  activated() {}
  deactivated() { S.clearSelection() }
  mouseMove() {}
  pressButton() { return true }
  /** releaseButton: the element under the cursor joins the sequence; a complete sequence makes the constraint. */
  releaseButton(): boolean {
    const pre = S.getPreselection()
    let pick: SelId | null = null
    if (pre.point >= 0) { const [g, p] = S.geoVertexIndex(pre.point); pick = { geoId: g, pos: p } }
    else if (pre.curve !== null) pick = { geoId: pre.curve, pos: NONE }
    else if (pre.cross === 0) pick = { geoId: -1, pos: START }
    else if (pre.cross === 1) pick = { geoId: H_AXIS, pos: NONE }
    else if (pre.cross === 2) pick = { geoId: V_AXIS, pos: NONE }
    if (!pick) return true
    const trial = [...this.seq, pick]
    const matches = (q: SelId[], s: string[]) => q.length <= s.length && q.every((x, i) => selType(x).includes(s[i]))
    const ok = this.cmd.sequences.filter((s) => matches(trial, s))
    if (!ok.length) { this.seq = []; S.clearSelection(); return true }
    this.seq = trial
    S.addSelection(pick.pos === NONE ? SK.edgeName(pick.geoId) : isRoot(pick) ? 'RootPoint' : SK.vertexName(S.vertexIndexOf(pick.geoId, pick.pos)))
    if (ok.some((s) => s.length === trial.length)) {
      const run = trial
      this.seq = []
      S.clearSelection()
      this.cmd.run(run)
      S.clearSelection()
    }
    return true
  }
  pressRightButton() { this.quit() }
  registerPressedKey(pressed: boolean, key: string) { if (key === 'Escape' && !pressed) { if (this.seq.length) { this.seq = []; S.clearSelection() } else this.quit() } return key === 'Escape' }
  private quit() { S.purgeHandler() }
  cursor() { return { svg: 'Sketcher_Crosshair', tail: [CONSTRAINT_CURSOR[this.cmd.name]].filter(Boolean) } }
  hints() { return [{ message: '%1 pick elements', keys: ['LMB'] }] }
}
