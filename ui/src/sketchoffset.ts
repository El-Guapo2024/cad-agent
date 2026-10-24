// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Sketcher/Gui/DrawSketchHandlerOffset.h: 2023 Pierre-Louis Boyer
//   src/Mod/Sketcher/Gui/CommandSketcherTools.cpp: 2014 Abdullah Tahiri
// Sketcher_Offset (Z, T): the selected lines, arcs and circles grouped into continuous curves (generatevCC), their
// offset by OCCT's BRepOffsetAPI_MakeOffset at the cursor's distance (the sketch kernel: cad_agent/sketch_offset.py),
// previewed as the cursor moves and made on a click: the offset curves joined (Coincident, Tangent where an arc meets
// its neighbour tangentially), the originals deleted (U, "Delete original geometries"), or the offset tied to them
// by a distance (J, "Add offset constraint": construction lines, Parallel, Perpendicular, Equal). M switches the join
// between Arc and Intersection.
import type { Geo, XY } from './solver'
import * as SK from './sketch'
import { type Constraint, type PointPos, NONE, START, END, MID, constraint } from './sketch'
import * as S from './sketcher'
import * as OPS from './sketchops'
import { DefaultHandler } from './sketchtools'
import { tryKernel, withKernel, runOp, type Kernel } from './sketchkernel'
import './sketchkernelapi'
import { report } from './store'

const CONFUSION = 1e-7, INTERSECTION = CONFUSION * 0.01
type Doc = OPS.Doc
const sub = (a: XY, b: XY): XY => [a[0] - b[0], a[1] - b[1]], add = (a: XY, b: XY): XY => [a[0] + b[0], a[1] + b[1]]
const len = (a: XY) => Math.hypot(a[0], a[1])
const cross = (a: XY, b: XY) => a[0] * b[1] - a[1] * b[0]
/** Base::Vector3d::ProjectToLine(p, line): from p to its foot on the line through the origin along `line`. */
const projectToLine = (p: XY, d: XY): XY => { const t = (p[0] * d[0] + p[1] * d[1]) / (d[0] * d[0] + d[1] * d[1]); return [d[0] * t - p[0], d[1] * t - p[1]] }
const plain = (g: Geo): Geo => { const { construction: _c, ...r } = g as Geo & { construction?: boolean }; void _c; return r as Geo }
const arcPoint = (g: Extract<Geo, { type: 'ArcOfCircle' }>, a: number): XY => [g.center[0] + g.radius * Math.cos(a), g.center[1] + g.radius * Math.sin(a)]

/** getFirstSecondPoints: a line's, an arc's (counter-clockwise) or a B-spline's ends. */
function ends(g: Geo | undefined): [XY, XY] | null {
  if (!g) return null
  if (g.type === 'LineSegment') return [g.start, g.end]
  if (g.type === 'ArcOfCircle') return [arcPoint(g, g.start_angle), arcPoint(g, g.end_angle)]
  if (g.type === 'ArcOfEllipse' || g.type === 'ArcOfHyperbola' || g.type === 'ArcOfParabola' || g.type === 'BSplineCurve') {
    const s = SK.getPoint([g], 0, START), e = SK.getPoint([g], 0, END)
    return s && e ? [s, e] : null
  }
  return null
}
const near = (a: XY, b: XY) => len(sub(a, b)) < CONFUSION
/** areCoincident: the curves' ends meet (positions, not constraints). */
function areCoincident(geo: (g: number) => Geo | undefined, a: number, b: number) {
  const p = ends(geo(a)), q = ends(geo(b))
  return !!p && !!q && (near(p[0], q[0]) || near(p[0], q[1]) || near(p[1], q[0]) || near(p[1], q[1]))
}
/** generatevCC: the curves in continuous chains, each in order along it (a circle on its own). */
export function generatevCC(geo: (g: number) => Geo | undefined, ids: number[]): number[][] {
  const vcc: number[][] = []
  for (const id of ids) {
    const g = geo(id)
    if (g?.type === 'Circle' || g?.type === 'Ellipse') { vcc.push([id]); continue }
    let inserted = false, insertedIn = -1
    for (let j = 0; j < vcc.length; j++) {
      for (let k = 0; k < vcc[j].length; k++) {
        if (!areCoincident(geo, id, vcc[j][k])) continue
        if (inserted && insertedIn !== j) {
          if (vcc[insertedIn][0] === id) {
            if (k === 0) vcc[j].reverse()
            vcc[j].push(...vcc[insertedIn])
            vcc.splice(insertedIn, 1)
          } else {
            if (k !== 0) vcc[j].reverse()
            vcc[insertedIn].push(...vcc[j])
            vcc.splice(j, 1)
          }
          j--
        } else {
          if (k === vcc[j].length - 1) vcc[j].push(id)
          else vcc[j].splice(k, 0, id)
          insertedIn = j
          inserted = true
        }
        break
      }
    }
    if (!inserted) vcc.push([id])
  }
  return vcc
}

/** The offset the kernel makes of the chains, at the cursor (or at a length). */
type Made = { length: number; on_wire: XY | null; geometry: (Geo | null)[] }
function request(chains: Geo[][], join: number, at: { point: XY } | { length: number }) {
  return { op: 'offset' as const, curves: chains, join, ...at }
}

/** checkForCoincidence: the first two Coincident (or, tangentOnly, Tangent) end-to-end constraints between two curves. */
function checkForCoincidence(cs: Constraint[], g1: number, g2: number, tangentOnly = false) {
  const out = { firstPos1: NONE as PointPos, secondPos1: NONE as PointPos, firstPos2: NONE as PointPos, secondPos2: NONE as PointPos }
  let found = false
  for (const c of cs) {
    if (((tangentOnly || c.type !== 'Coincident') && c.type !== 'Tangent') || c.firstPos === MID || c.firstPos === NONE || c.secondPos === MID || c.secondPos === NONE) continue
    if ((c.first === g1 && c.second === g2) || (c.first === g2 && c.second === g1)) {
      const a = c.first === g1 ? c.firstPos : c.secondPos, b = c.first === g2 ? c.firstPos : c.secondPos
      if (!found) { out.firstPos1 = a; out.secondPos1 = b; found = true } else { out.firstPos2 = a; out.secondPos2 = b; break }
    }
  }
  return out
}

/** createOffset's steps after the curves are added, on the sketch: jointOffsetCurves, then deleteOriginalGeometries
 *  or makeOffsetConstraint. */
export function finishOffset(d: Doc, sources: number[], newIds: number[], length: number, deleteOriginal: boolean, offsetConstraint: boolean) {
  const geo = (g: number) => d.geometry[g]
  // jointOffsetCurves
  const joints: Constraint[] = []
  for (let i = 0; i < newIds.length - 1; i++) for (let j = i + 1; j < newIds.length; j++) {
    const a = ends(geo(newIds[i])), b = ends(geo(newIds[j]))
    if (!a || !b) continue
    let pi: PointPos | null = null, pj: PointPos = NONE
    if (near(a[0], b[0])) { pi = START; pj = START } else if (near(a[0], b[1])) { pi = START; pj = END }
    else if (near(a[1], b[0])) { pi = END; pj = START } else if (near(a[1], b[1])) { pi = END; pj = END }
    if (pi === null) continue
    joints.push(constraint(needTangent(d, newIds[i], newIds[j], pi, pj) ? 'Tangent' : 'Coincident', newIds[i], pi, newIds[j], pj))
  }
  d.constraints = [...d.constraints, ...joints]
  if (deleteOriginal) OPS.delGeometries(d, sources.filter((g) => g >= 0)) // delGeometries (an external one: delExternal, not here)
  else if (offsetConstraint) makeOffsetConstraint(d, sources, newIds, length)
}
/** needTangent: an arc meeting a line or an arc with the same direction there. */
function needTangent(d: Doc, g1: number, g2: number, p1: PointPos, p2: PointPos): boolean {
  const a = d.geometry[g1], b = d.geometry[g2]
  if (a.type !== 'ArcOfCircle' && b.type !== 'ArcOfCircle') return false
  const perp = (g: Geo, pos: PointPos): XY | null => {
    if (g.type === 'ArcOfCircle') { const p = arcPoint(g, pos === START ? g.start_angle : g.end_angle), r = sub(g.center, p); return [-r[1], r[0]] }
    if (g.type === 'LineSegment') return sub(g.start, g.end)
    return null
  }
  const u = perp(a, p1), v = perp(b, p2)
  if (!u || !v) return false
  return Math.abs(cross(u, v)) < CONFUSION
}
/** makeOffsetConstraint: each offset curve tied to the curve it offsets (Coincident centres, Parallel lines), construction
 *  lines across the gap (Perpendicular, on both curves, Equal to the first) and a Distance on the first; with a single
 *  such line, a Distance between the curves instead. */
function makeOffsetConstraint(d: Doc, sources: number[], newIds: number[], length: number) {
  const geo = (g: number) => d.geometry[g]
  const highest = d.geometry.length - 1
  const stream: Constraint[] = [], lines: Constraint[] = []
  const vcco = generatevCC(geo, newIds)
  let cand1 = 0, cand2 = 0, newCount = 0, prevCount = 0
  const toAdd: Geo[] = []
  const areTangentCoincident = (a: number, b: number) => checkForCoincidence(d.constraints, a, b, true).firstPos1 !== NONE
  const isCurveClosed = (curve: number[]) => {
    if (curve.length > 2) return areCoincident(geo, curve[0], curve[curve.length - 1])
    if (curve.length === 2) { const c = checkForCoincidence(d.constraints, curve[0], curve[1]); return c.firstPos1 !== NONE && c.firstPos2 !== NONE }
    return false
  }
  const constructionLine = (a: XY, b: XY) => { toAdd.push({ type: 'LineSegment', start: a, end: b, construction: true }); newCount++ }
  for (const curve of vcco) {
    const closed = isCurveClosed(curve)
    let atLeastOneLine = false, rerunFirstAfterThis = false, rerunningFirst = false, inTangentGroup = false
    for (let j = 0; j < curve.length; j++) {
      let createLine = true, forceCreate = false
      if (!inTangentGroup && (!closed || j !== 0 || rerunningFirst)) { createLine = true; atLeastOneLine = true } else createLine = false
      if (j + 1 < curve.length) inTangentGroup = areTangentCoincident(curve[j], curve[j + 1])
      else if (j === curve.length - 1 && closed) {
        inTangentGroup = areTangentCoincident(curve[j], curve[0])
        if (inTangentGroup) { if (!atLeastOneLine) { createLine = true; forceCreate = true } } else rerunFirstAfterThis = true
      }
      const g = geo(curve[j])
      for (const id of sources) {
        const g2 = geo(id)
        if (!g2) continue // an external source: the copy here holds the sketch's own geometry only
        if (g.type === 'Circle' && g2.type === 'Circle') {
          if (near(g.center, g2.center)) {
            stream.push(constraint('Coincident', curve[j], MID, id, MID))
            constructionLine([g.center[0] + g.radius, g.center[1]], [g2.center[0] + g2.radius, g2.center[1]])
            const n = highest + newCount
            lines.push(constraint('Perpendicular', n, NONE, curve[j]), constraint('PointOnObject', n, START, curve[j]), constraint('PointOnObject', n, END, id))
            cand1 = curve[j]; cand2 = id
            break
          }
        } else if (g.type === 'LineSegment' && g2.type === 'LineSegment') {
          const p1 = [g.start, g.end], p2 = [g2.start, g2.end]
          if (Math.abs(cross(sub(p1[1], p1[0]), sub(p2[1], p2[0]))) < INTERSECTION) {
            const proj = projectToLine(sub(p1[0], p2[0]), sub(p2[1], p2[0]))
            if (len(proj) - Math.abs(length) < CONFUSION) {
              if (!forceCreate && !rerunningFirst) stream.push(constraint('Parallel', curve[j], NONE, id))
              if (createLine) {
                constructionLine(p1[0], add(p1[0], proj))
                const n = highest + newCount
                lines.push(constraint('Perpendicular', n, NONE, curve[j]), constraint('Coincident', n, START, curve[j], START), constraint('PointOnObject', n, END, id))
                cand1 = curve[j]; cand2 = id
              }
              break
            }
          }
        } else if (g.type === 'ArcOfCircle') {
          const c1 = g.center
          if (g2.type === 'ArcOfCircle') {
            const p3 = arcPoint(g2, g2.start_angle), p4 = arcPoint(g2, g2.end_angle)
            if (near(c1, g2.center)) {
              stream.push(constraint('Coincident', curve[j], MID, id, MID))
              if (createLine) {
                constructionLine([c1[0] + g.radius, c1[1]], [g2.center[0] + g2.radius, g2.center[1]])
                const n = highest + newCount
                lines.push(constraint('Perpendicular', n, NONE, curve[j]), constraint('PointOnObject', n, START, curve[j]), constraint('PointOnObject', n, END, id))
                cand1 = curve[j]; cand2 = id
              }
              break
            } else if (near(c1, p3) || near(c1, p4)) {
              stream.push(constraint('Coincident', curve[j], MID, id, near(c1, p3) ? START : END))
              if (forceCreate) stream.push(constraint('Radius', curve[j], NONE, SK.GEO_UNDEF, NONE, SK.GEO_UNDEF, NONE, length))
              break
            }
          } else if (g2.type === 'LineSegment' || g2.type === 'BSplineCurve' || g2.type === 'ArcOfEllipse' || g2.type === 'ArcOfHyperbola' || g2.type === 'ArcOfParabola') {
            const e = ends(g2)
            if (e) {
              const s = near(c1, e[0]), t = near(c1, e[1])
              if (s || t) { stream.push(constraint('Coincident', curve[j], MID, id, s ? START : END)); cand1 = curve[j]; cand2 = id; break }
            }
          }
        }
      }
      if (newCount !== prevCount) {
        prevCount = newCount
        if (newCount !== 1) stream.push(constraint('Equal', highest + newCount, NONE, highest + 1))
      }
      if (rerunningFirst) break
      if (rerunFirstAfterThis) { j = -1; rerunningFirst = true; rerunFirstAfterThis = false }
    }
  }
  const abs = Math.abs(length)
  if (newCount >= 2) {
    stream.push(constraint('Distance', highest + 1, NONE, SK.GEO_UNDEF, NONE, SK.GEO_UNDEF, NONE, abs))
    d.geometry = [...d.geometry, ...toAdd]
    d.constraints = [...d.constraints, ...lines]
  } else {
    // a single construction line is not needed
    const g = geo(cand1)
    if (g?.type === 'Circle') stream.push(constraint('Distance', cand1, NONE, cand2, NONE, SK.GEO_UNDEF, NONE, abs))
    else if (g?.type === 'LineSegment') stream.push(constraint('Distance', cand1, START, cand2, NONE, SK.GEO_UNDEF, NONE, abs))
    else if (g?.type === 'ArcOfCircle') {
      const g2 = geo(cand2)
      if (g2?.type === 'ArcOfCircle') stream.push(constraint('Distance', cand1, START, cand2, START, SK.GEO_UNDEF, NONE, abs))
      else if (g2?.type === 'LineSegment') stream.push(constraint('Distance', cand1, MID, cand1, START, SK.GEO_UNDEF, NONE, abs))
    }
  }
  d.constraints = [...d.constraints, ...stream]
}

/** createOffset on a sketch: the kernel's offset curves added (not construction; the ids of the edges it skips are
 *  counted all the same), then finishOffset. false when there is nothing ("Offset could not be created"). */
export function createOffset(d: Doc, sources: number[], made: Made, deleteOriginal: boolean, offsetConstraint: boolean): boolean {
  const first = d.geometry.length
  const ids: number[] = [], geos: Geo[] = []
  made.geometry.forEach((g, i) => { if (g) { geos.push(plain(g)); ids.push(first + i) } })
  if (!ids.length) return false
  d.geometry = [...d.geometry, ...geos]
  finishOffset(d, sources, ids, made.length, deleteOriginal, offsetConstraint)
  return true
}

// ── the tool (DrawSketchHandlerOffset) ───────────────────────────────────────────────────────────────────────────
export class OffsetHandler extends DefaultHandler {
  readonly toolName = 'DSH_Offset'
  protected readonly states = 1
  protected readonly methods = 2
  private deleteOriginal = false
  private offsetConstraint = false
  private chains: Geo[][]
  private endpoint: XY = [0, 0]
  private made: Made | null = null
  private busy = false
  constructor(private sources: number[]) {
    super()
    this.continuousMode = false
    const all = S.getGeometry()
    this.chains = generatevCC((g) => all[g], sources).map((cc) => cc.map((g) => plain(all[g])))
  }
  crosshair() { return 'Sketcher_Pointer_Create_Offset' }
  hints() { return [this.hint('%1 set offset direction and distance', ['LMB'])] }
  registerPressedKey(pressed: boolean, key: string): boolean {
    // the tool widget's check boxes: U deletes the originals, J adds the offset constraint (not both)
    if (key === 'U' || key === 'J') {
      if (!pressed) {
        if (key === 'U') { this.deleteOriginal = !this.deleteOriginal; if (this.deleteOriginal) this.offsetConstraint = false }
        else { this.offsetConstraint = !this.offsetConstraint; if (this.offsetConstraint) this.deleteOriginal = false }
      }
      return true
    }
    return super.registerPressedKey(pressed, key)
  }
  protected resetOnMethodChange() { return false }
  /** updateDataAndDrawToPosition: the length at the cursor (findOffsetLength), the offset drawn. */
  protected update(p: XY) {
    this.endpoint = p
    const req = request(this.chains, this.method === 0 ? 0 : 2, { point: [p[0], p[1]] })
    const made = tryKernel((k) => k(req) as unknown as Made, () => { if (this.state === 0) this.update(this.endpoint) })
    if (made) this.made = made
    const geos = (this.made?.geometry ?? []).filter((g): g is Geo => !!g)
    S.setEdit({ curves: this.made && Math.abs(this.made.length) > CONFUSION ? geos.map((g) => SK.polyline(g)) : [], construction: false })
  }
  private offsetAt(k: Kernel): Made { return k(request(this.chains, this.method === 0 ? 0 : 2, { point: [this.endpoint[0], this.endpoint[1]] })) as unknown as Made }
  protected finish(): boolean {
    if (!this.isLast) return false
    if (this.busy) return true
    // the offset at the click is OCCT's: fetch it, then the commands as FreeCAD's tool runs them
    this.busy = true
    withKernel((k) => this.offsetAt(k)).then(() => { this.busy = false; super.finish() },
      (e) => { this.busy = false; report('err', `Offset Error: ${e instanceof Error ? e.message : String(e)}`); S.purgeHandler() })
    return true
  }
  protected executeCommands() {
    runOp((k) => this.offsetAt(k), (made) => {
      if (Math.abs(made.length) <= CONFUSION) return
      const d: Doc = { geometry: S.getGeometry().map((g) => ({ ...g })), constraints: S.getConstraints().map((c) => ({ ...c })) }
      if (!createOffset(d, this.sources, made, this.deleteOriginal, this.offsetConstraint)) { report('err', 'Offset Error: Offset could not be created.'); return }
      S.openCommand('Offset')
      S.setGeometry(d.geometry); S.setConstraints(d.constraints)
      S.commitCommand()
    }, (e) => report('err', `Offset Error: ${e instanceof Error ? e.message : String(e)}`))
  }
  protected onReset() { this.made = null }
}

/** CmdSketcherOffset: the selected edges that are lines, arcs or circles (not internal geometry). */
export function runOffset() {
  const all = S.getGeometry(), cs = S.getConstraints()
  const ids: number[] = []
  for (const n of S.getSelection()) {
    let g: number | null = null
    if (n.startsWith('Edge')) g = Number(n.slice(4)) - 1
    else if (n.startsWith('ExternalEdge')) g = SK.edgeId(n)
    if (g === null) continue
    const geo = all[g]
    if (!geo || geo.type === 'Point' || geo.type === 'BSplineCurve' || geo.type === 'Ellipse' || geo.type === 'ArcOfEllipse'
      || geo.type === 'ArcOfHyperbola' || geo.type === 'ArcOfParabola') continue
    if (cs.some((c) => c.type === 'InternalAlignment' && c.first === g)) continue
    ids.push(g)
  }
  if (ids.length) S.activateHandler(new OffsetHandler(ids))
  else {
    S.clearSelection()
    report('err', 'Invalid selection: Selection has no valid geometries. B-splines and points are not supported yet.')
  }
}
