// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Sketcher/Gui/DrawSketchHandler.cpp: 2010 Jürgen Riegel
//   src/Mod/Sketcher/Gui/DrawSketchDefaultHandler.h: 2022 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/DrawSketchController.h: 2023 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/DrawSketchControllableHandler.h: 2023 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/DrawSketchHandlerPoint.h: 2022 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/DrawSketchHandlerLine.h: 2022 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/DrawSketchHandlerLineSet.h: 2022 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/DrawSketchHandlerArc.h: 2022 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/DrawSketchHandlerCircle.h: 2022 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/DrawSketchHandlerRectangle.h: 2022 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/DrawSketchHandlerSlot.h: 2022 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/DrawSketchHandlerPolygon.h: 2022 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/Utils.cpp: 2021 Abdullah Tahiri
// The Sketcher's geometry tools: DrawSketchHandler (what an auto-constraint the cursor suggests, its cursor icons,
// how a suggestion becomes a constraint, redundant ones dropped), DrawSketchDefaultHandler's state machine (each click
// the next state, continuous mode, Esc and the right button, M for the next construction method), and the handlers:
// point, line, polyline, arc, circle, rectangle (corner, centred, rounded), slot and regular polygon, each making the
// geometry and constraints FreeCAD's makes for the same clicks.
import type { Geo, XY } from './solver'
import * as SK from './sketch'
import { type Constraint, type ConstraintType, type PointPos, NONE, START, END, MID, GEO_UNDEF, H_AXIS, V_AXIS, RT_PNT, constraint } from './sketch'
import * as S from './sketcher'

/** AutoConstraint: a suggested constraint, to an element (GeoId and PointPos). */
export type AutoConstraint = { type: ConstraintType; geoId: number; posId: PointPos }
/** AutoConstraint::TargetType. */
export type Target = 'vertex' | 'curve' | 'vertexNoTangency'
const CONFUSION = 1e-7, SQ_CONFUSION = CONFUSION * CONFUSION
const deg = (d: number) => (d * Math.PI) / 180
const angleDistance = (a: number, b: number) => Math.abs(Math.atan2(Math.sin(a - b), Math.cos(a - b)))
const isParallelAngle = (r: number, c: number) => { const d = angleDistance(r, c); return d < deg(2) || Math.abs(d - Math.PI) < deg(2) }
const isPerpendicularAngle = (r: number, c: number) => Math.abs(angleDistance(r, c) - Math.PI / 2) < deg(2)
const sub = (a: XY, b: XY): XY => [a[0] - b[0], a[1] - b[1]], add = (a: XY, b: XY): XY => [a[0] + b[0], a[1] + b[1]]
const mul = (a: XY, k: number): XY => [a[0] * k, a[1] * k], len = (a: XY) => Math.hypot(a[0], a[1]), sqr = (a: XY) => a[0] * a[0] + a[1] * a[1]
const dot = (a: XY, b: XY) => a[0] * b[0] + a[1] * b[1]
const angleOf = (a: XY) => Math.atan2(a[1], a[0])
/** Base::Vector2d::GetAngle: the angle between two vectors, 0 to π. */
const getAngle = (a: XY, b: XY) => { const l = len(a) * len(b); return l ? Math.acos(Math.max(-1, Math.min(1, dot(a, b) / l))) : NaN }
const normalize = (a: XY): XY => { const l = len(a) || 1; return [a[0] / l, a[1] / l] }
/** Base::Vector2d::ProjectToLine: the projection of p onto the direction d. */
const project = (p: XY, d: XY): XY => mul(d, dot(p, d) / sqr(d))

/** Part::Geom2dCircle::getCircleCenter. */
function circleCenter(a: XY, b: XY, c: XY): XY {
  const d = 2 * (a[0] * (b[1] - c[1]) + b[0] * (c[1] - a[1]) + c[0] * (a[1] - b[1]))
  const ux = ((sqr(a)) * (b[1] - c[1]) + sqr(b) * (c[1] - a[1]) + sqr(c) * (a[1] - b[1])) / d
  const uy = ((sqr(a)) * (c[0] - b[0]) + sqr(b) * (a[0] - c[0]) + sqr(c) * (b[0] - a[0])) / d
  return [ux, uy]
}
/** SketcherGui::areCollinear. */
const areCollinear = (a: XY, b: XY, c: XY) => Math.abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])) < CONFUSION

const ICONS: Partial<Record<ConstraintType, string>> = {
  Horizontal: 'Constraint_Horizontal', Vertical: 'Constraint_Vertical', Coincident: 'Constraint_PointOnPoint', PointOnObject: 'Constraint_PointOnObject',
  Symmetric: 'Constraint_Symmetric', Tangent: 'Constraint_Tangent', Perpendicular: 'Constraint_Perpendicular', Parallel: 'Constraint_Parallel',
}

/** DrawSketchHandler: the auto-constraints and the cursor. */
export abstract class DrawSketchHandler implements S.Handler {
  abstract readonly toolName: string
  protected cursorTail: string[] = []
  protected lineExtensionHint: { valid: boolean; start: XY; end: XY } = { valid: false, start: [0, 0], end: [0, 0] }
  protected tangentHint: { valid: boolean; active: boolean; geoId: number; posId: PointPos; start: XY; direction: XY } = { valid: false, active: false, geoId: GEO_UNDEF, posId: NONE, start: [0, 0], direction: [0, 0] }
  protected parPerpRefGeoId = GEO_UNDEF
  protected parPerpActiveLine = -1
  protected parPerpFromEndpoint = false
  protected lastHoveredGeoId = GEO_UNDEF
  private hoverTimer: number | undefined

  activated() {}
  deactivated() { clearTimeout(this.hoverTimer) }
  abstract mouseMove(pos: XY): void
  abstract pressButton(pos: XY): boolean
  abstract releaseButton(pos: XY): boolean
  pressRightButton(_pos: XY) { this.cancelCurrentAction() }
  registerPressedKey(pressed: boolean, key: string): boolean { if (key === 'Escape' && !pressed) { this.cancelCurrentAction(); return true } return false }
  cancelCurrentAction() { this.quit() }
  /** DrawSketchHandler::quit: the tool goes. */
  quit() { S.purgeHandler() }
  abstract crosshair(): string
  cursor() { return { svg: this.crosshair(), tail: this.cursorTail } }
  hints(): { message: string; keys: string[] }[] { return [] }
  isConstructionMode() { return S.isConstructionMode() }
  getStartPointOfCurrentSegment(): XY | null { return null }

  // ── seekAutoConstraint and its parts ──
  /** getPreselectionData: the GeoId and PointPos under the cursor, and the direction of a line there. */
  protected preselectionData() {
    const pre = S.getPreselection(), geo = S.getGeometry()
    const out = { geoId: GEO_UNDEF, posId: NONE as PointPos, hitDir: [0, 0] as XY, isLine: false }
    if (pre.point >= 0) { const [g, p] = S.geoVertexIndex(pre.point); out.geoId = g; out.posId = p }
    else if (pre.curve !== null && !SK.isAxisId(pre.curve)) { // an edge of the sketch or an external one
      out.geoId = pre.curve
      const g = geo[pre.curve]
      if (SK.isLine(g)) { out.hitDir = sub(g.end, g.start); out.isLine = true }
    } else if (pre.cross === 0) { out.geoId = RT_PNT; out.posId = START }
    else if (pre.cross === 1) { out.geoId = H_AXIS; out.hitDir = [1, 0]; out.isLine = true }
    else if (pre.cross === 2) { out.geoId = V_AXIS; out.hitDir = [0, 1]; out.isLine = true }
    return out
  }
  private isLineCenter(g: number, p: XY) {
    const e = S.getGeometry()[g]
    if (!SK.isLine(e)) return false
    return len(sub(p, mul(add(e.start, e.end), 0.5))) < len(sub(e.end, e.start)) * 0.05
  }
  private seekPreselection(sug: AutoConstraint[], pos: XY, dir: XY, type: Target) {
    const pre = this.preselectionData()
    if (pre.geoId === GEO_UNDEF) return
    let t: ConstraintType | null = null
    if (type === 'vertex' || type === 'vertexNoTangency') t = pre.posId === NONE ? (this.isLineCenter(pre.geoId, pos) ? 'Symmetric' : 'PointOnObject') : 'Coincident'
    else if (type === 'curve' && pre.posId !== NONE) t = 'PointOnObject'
    else if (type === 'curve') t = 'Tangent'
    if (t === 'Tangent' && pre.isLine) {
      if (len(dir) < 1e-8 || len(pre.hitDir) < 1e-8) return
      if (Math.abs(dot(normalize(dir), normalize(pre.hitDir))) > 0.995) return
    }
    if (t) sug.push({ type: t, geoId: pre.geoId, posId: pre.posId })
  }
  /** getAutoConstraintSearchDistance: 0.1 × ViewProviderSketch::getScaleFactor. */
  protected searchDistance() { return 0.1 * S.getScaleFactor() }
  private seekLineExtension(sug: AutoConstraint[], pos: XY, type: Target) {
    if (type !== 'vertex' && type !== 'vertexNoTangency') return false
    if (sug.some((c) => c.type === 'Coincident' || c.type === 'PointOnObject' || c.type === 'Symmetric')) return false
    const sd = this.searchDistance()
    let best = sd * sd, bestGeo = GEO_UNDEF, anchor: XY = [0, 0], proj: XY = [0, 0]
    S.getGeometry().forEach((g, i) => {
      if (!SK.isLine(g)) return
      const d = sub(g.end, g.start), l2 = sqr(d)
      if (l2 <= SQ_CONFUSION) return
      const t = dot(sub(pos, g.start), d) / l2
      if (t >= 0 && t <= 1) return
      const p = add(g.start, mul(d, t)), d2 = sqr(sub(pos, p))
      if (d2 > best) return
      best = d2; bestGeo = i; anchor = t < 0 ? g.start : g.end; proj = p
    })
    if (bestGeo === GEO_UNDEF) return false
    const sc = (p: XY) => S.toScreen(p)
    for (const p of [anchor, proj]) { const [x, y] = sc(p); if (x < 0 || y < 0 || x > innerWidth || y > innerHeight) return false }
    sug.push({ type: 'PointOnObject', geoId: bestGeo, posId: NONE })
    this.lineExtensionHint = { valid: true, start: anchor, end: proj }
    return true
  }
  protected lineExtensionSnapPoint(): XY | null { return this.lineExtensionHint.valid ? this.lineExtensionHint.end : null }
  private updateTangentHint(): boolean {
    this.tangentHint = { valid: false, active: false, geoId: GEO_UNDEF, posId: NONE, start: [0, 0], direction: [0, 0] }
    const start = this.getStartPointOfCurrentSegment()
    if (!start) return false
    const geo = S.getGeometry()
    for (let g = geo.length - 1; g >= 0; g--) {
      const e = geo[g]
      if (!SK.isArc(e)) continue
      const as = SK.getPoint(geo, g, START)!, ae = SK.getPoint(geo, g, END)!
      let posId: PointPos, direction: XY
      if (sqr(sub(as, start)) < SQ_CONFUSION) { posId = START; const r = sub(as, e.center); direction = [-r[1], r[0]] }
      else if (sqr(sub(ae, start)) < SQ_CONFUSION) { posId = END; const r = sub(ae, e.center); direction = [r[1], -r[0]] }
      else continue
      if (sqr(direction) <= SQ_CONFUSION) return false
      this.tangentHint = { valid: true, active: false, geoId: g, posId, start, direction: normalize(direction) }
      return true
    }
    return false
  }
  private closeToTangentHint(dir: XY) {
    if (!this.tangentHint.valid || sqr(dir) <= SQ_CONFUSION) return false
    return isParallelAngle(angleOf(this.tangentHint.direction), angleOf(dir))
  }
  /** snapToTangentHint: the cursor onto the tangent at the arc end the segment starts from. */
  protected snapToTangentHint(p: XY): XY | null {
    if (!this.updateTangentHint()) return null
    const d = sub(p, this.tangentHint.start)
    if (sqr(d) <= SQ_CONFUSION || !this.closeToTangentHint(d)) return null
    this.tangentHint.active = true
    return add(this.tangentHint.start, project(d, this.tangentHint.direction))
  }
  private updateParPerpEndpointHint(): boolean {
    const start = this.getStartPointOfCurrentSegment()
    if (!start) return false
    const geo = S.getGeometry()
    if (this.parPerpRefGeoId !== GEO_UNDEF) {
      if (!this.parPerpFromEndpoint) return true
      const e = geo[this.parPerpRefGeoId]
      if (SK.isLine(e) && (sqr(sub(e.start, start)) < SQ_CONFUSION || sqr(sub(e.end, start)) < SQ_CONFUSION)) return true
      this.parPerpRefGeoId = GEO_UNDEF; this.parPerpActiveLine = -1; this.parPerpFromEndpoint = false
    }
    for (let g = geo.length - 1; g >= 0; g--) {
      const e = geo[g]
      if (!SK.isLine(e)) continue
      const d = sub(e.end, e.start)
      if (sqr(d) <= SQ_CONFUSION || Math.abs(d[0]) < CONFUSION || Math.abs(d[1]) < CONFUSION) continue
      if (sqr(sub(e.start, start)) < SQ_CONFUSION || sqr(sub(e.end, start)) < SQ_CONFUSION) {
        this.parPerpRefGeoId = g; this.lastHoveredGeoId = g; this.parPerpFromEndpoint = true; clearTimeout(this.hoverTimer)
        return true
      }
    }
    return false
  }
  /** snapToParallelPerpendicularHint: the cursor onto the guide parallel or perpendicular to the reference line. */
  protected snapToParPerpHint(p: XY): XY | null {
    this.parPerpActiveLine = -1
    if (this.parPerpRefGeoId === GEO_UNDEF) { this.updateParPerpEndpointHint(); if (this.parPerpRefGeoId === GEO_UNDEF) return null }
    const start = this.getStartPointOfCurrentSegment()
    if (!start || len(sub(p, start)) < CONFUSION) return null
    const e = S.getGeometry()[this.parPerpRefGeoId]
    if (!SK.isLine(e)) return null
    const cur = sub(p, start)
    const ld = normalize(sub(e.end, e.start)), pd: XY = [-ld[1], ld[0]]
    let dir: XY
    if (isParallelAngle(angleOf(ld), angleOf(cur))) { dir = ld; this.parPerpActiveLine = 0 }
    else if (isPerpendicularAngle(angleOf(ld), angleOf(cur))) { dir = pd; this.parPerpActiveLine = 1 }
    else return null
    return add(start, project(cur, dir))
  }
  private seekAlignment(sug: AutoConstraint[], dir: XY) {
    const a = Math.abs(Math.atan2(dir[1], dir[0]))
    let c: AutoConstraint | null = null
    if (a < deg(2) || Math.PI - a < deg(2)) c = { type: 'Horizontal', geoId: GEO_UNDEF, posId: NONE }
    else if (Math.abs(a - Math.PI / 2) < deg(2)) c = { type: 'Vertical', geoId: GEO_UNDEF, posId: NONE }
    else if (this.parPerpRefGeoId !== GEO_UNDEF) {
      const e = S.getGeometry()[this.parPerpRefGeoId]
      if (SK.isLine(e)) {
        const ld = sub(e.end, e.start)
        if (Math.abs(ld[0]) > CONFUSION && Math.abs(ld[1]) > CONFUSION) {
          const la = angleOf(ld), da = angleOf(dir)
          const t: ConstraintType | null = isParallelAngle(la, da) ? 'Parallel' : isPerpendicularAngle(la, da) ? 'Perpendicular' : null
          if (t) { c = { type: t, geoId: this.parPerpRefGeoId, posId: NONE }; this.parPerpActiveLine = t === 'Parallel' ? 0 : 1 }
        }
      }
    }
    if (c) sug.push(c)
    return !!c
  }
  private seekTangent(sug: AutoConstraint[], pos: XY, dir: XY): boolean {
    if (this.tangentHint.valid && this.closeToTangentHint(dir)) {
      sug.push({ type: 'Tangent', geoId: this.tangentHint.geoId, posId: this.tangentHint.posId })
      this.tangentHint.active = true
      return true
    }
    let tangId = GEO_UNDEF, tanPos: PointPos = NONE, dev = this.searchDistance()
    const start = sub(pos, dir)
    const removeCoincident = (g: number, p: PointPos) => { for (let i = sug.length - 1; i >= 0; i--) if (sug[i].type === 'Coincident' && sug[i].geoId === g && sug[i].posId === p) sug.splice(i, 1) }
    const geo = S.getGeometry()
    geo.forEach((e, i) => {
      if (!SK.isCircular(e)) return
      const c = (e as { center: XY }).center, r = (e as { radius: number }).radius
      if (dot(dir, sub(c, pos)) > 0 || dot(dir, sub(c, start)) < 0) return
      const projPnt = project(sub(c, pos), dir)
      // Base::Vector3d::ProjectToLine gives the perpendicular from the line to the point, not the foot
      const perp = sub(sub(c, pos), projPnt)
      const projDist = Math.abs(len(perp) - r)
      if (projDist >= dev) return
      if (SK.isCircle(e)) { tangId = i; dev = projDist; return }
      const as = SK.getPoint(geo, i, START)!, ae = SK.getPoint(geo, i, END)!
      if (sqr(sub(as, pos)) < SQ_CONFUSION) { tanPos = START; tangId = i; dev = projDist; removeCoincident(i, START) }
      else if (sqr(sub(as, start)) < SQ_CONFUSION) { tanPos = START; tangId = i; dev = projDist }
      else if (sqr(sub(ae, pos)) < SQ_CONFUSION) { tanPos = END; tangId = i; dev = projDist; removeCoincident(i, END) }
      else if (sqr(sub(ae, start)) < SQ_CONFUSION) { tanPos = END; tangId = i; dev = projDist }
      else {
        const arc = e as Extract<Geo, { type: 'ArcOfCircle' }>
        let a = Math.atan2(-perp[1], -perp[0])
        while (a < arc.start_angle) a += 2 * Math.PI
        if (a <= arc.end_angle) { tangId = i; dev = projDist }
      }
    })
    if (tangId === GEO_UNDEF) return false
    const match = this.tangentHint.valid && tangId === this.tangentHint.geoId && tanPos === this.tangentHint.posId
    if (match && !this.closeToTangentHint(dir)) return false
    sug.push({ type: 'Tangent', geoId: tangId, posId: tanPos })
    if (match) this.tangentHint.active = true
    return true
  }
  /** DrawSketchHandler::seekAutoConstraint. */
  seekAutoConstraint(sug: AutoConstraint[], pos: XY, dir: XY, type: Target = 'vertex'): number {
    sug.length = 0
    this.lineExtensionHint = { valid: false, start: [0, 0], end: [0, 0] }
    this.updateTangentHint()
    this.parPerpActiveLine = -1
    this.updateParPerpEndpointHint()
    // a non-axis line under the cursor for 400 ms becomes the parallel/perpendicular reference (startHoverTimer)
    const pre = this.preselectionData()
    const horOrVert = Math.abs(pre.hitDir[0]) < CONFUSION || Math.abs(pre.hitDir[1]) < CONFUSION
    if (pre.isLine && !horOrVert && pre.geoId !== GEO_UNDEF) {
      if (pre.geoId !== this.lastHoveredGeoId) {
        this.lastHoveredGeoId = pre.geoId
        clearTimeout(this.hoverTimer)
        this.hoverTimer = window.setTimeout(() => { if (this.lastHoveredGeoId !== GEO_UNDEF) { this.parPerpRefGeoId = this.lastHoveredGeoId; this.parPerpFromEndpoint = false; this.renderHints() } }, 400)
      }
    } else if (this.lastHoveredGeoId !== GEO_UNDEF) { this.lastHoveredGeoId = GEO_UNDEF; clearTimeout(this.hoverTimer) }
    this.seekPreselection(sug, pos, dir, type)
    this.seekLineExtension(sug, pos, type)
    if (len(dir) > 1e-8 && type !== 'curve') {
      const tangent = type !== 'vertexNoTangency' && this.seekTangent(sug, pos, dir)
      if (!tangent) this.seekAlignment(sug, dir)
    }
    return sug.length
  }
  /** seekAndRenderAutoConstraint: the suggestions, the hints drawn, the cursor's icons. */
  seekAndRender(sug: AutoConstraint[], pos: XY, dir: XY, type: Target = 'vertex') {
    const n = this.seekAutoConstraint(sug, pos, dir, type)
    this.renderHints()
    this.cursorTail = sug.map((c) => ICONS[c.type]).filter((x): x is string => !!x)
    S.applyCursor()
    return n
  }
  protected renderHints() {
    const lines: XY[][] = [], half = 1000 * S.getScaleFactor()
    let active = -1
    if (this.tangentHint.valid) { lines.push([sub(this.tangentHint.start, mul(this.tangentHint.direction, half)), add(this.tangentHint.start, mul(this.tangentHint.direction, half))]); if (this.tangentHint.active) active = 0 }
    const start = this.getStartPointOfCurrentSegment()
    const e = this.parPerpRefGeoId !== GEO_UNDEF ? S.getGeometry()[this.parPerpRefGeoId] : undefined
    if (start && SK.isLine(e)) {
      const ld = normalize(sub(e.end, e.start)), pd: XY = [-ld[1], ld[0]], first = lines.length
      lines.push([sub(start, mul(ld, half)), add(start, mul(ld, half))], [sub(start, mul(pd, half)), add(start, mul(pd, half))])
      if (this.parPerpActiveLine >= 0) active = first + this.parPerpActiveLine
    }
    S.setEdit({ extensionHint: this.lineExtensionHint.valid ? [this.lineExtensionHint.start, this.lineExtensionHint.end] : null, directionHints: { lines, active } })
  }
  protected resetParPerpHint() {
    this.parPerpRefGeoId = GEO_UNDEF; this.parPerpActiveLine = -1; this.parPerpFromEndpoint = false
    this.tangentHint = { valid: false, active: false, geoId: GEO_UNDEF, posId: NONE, start: [0, 0], direction: [0, 0] }
    this.lastHoveredGeoId = GEO_UNDEF; clearTimeout(this.hoverTimer)
    S.setEdit({ directionHints: { lines: [], active: -1 } })
  }

  /** generateOneAutoConstraintFromSuggestion: a suggestion on (geoId1, posId1) as a constraint, folding a coincidence
   *  and a tangency on the same points into one endpoint tangency. */
  generateOne(ac: AutoConstraint, geoId1: number, posId1: PointPos, out: Constraint[]): boolean {
    let g2 = ac.geoId, p2 = ac.posId
    const startOrEnd = (p: PointPos) => p === START || p === END
    switch (ac.type) {
      case 'Coincident': {
        if (posId1 === NONE) return true
        const t = startOrEnd(posId1) && startOrEnd(p2) ? out.find((c) => c.type === 'Tangent' && c.first === geoId1 && c.second === g2) : undefined
        if (t) { t.firstPos = posId1; t.secondPos = p2 }
        else out.push(constraint('Coincident', geoId1, posId1, g2, p2))
        return true
      }
      case 'PointOnObject': {
        let g1 = geoId1, ps1 = posId1
        if (ps1 === NONE) { [g1, g2] = [g2, g1]; [ps1, p2] = [p2, ps1] }
        const t = startOrEnd(ps1) ? out.find((c) => c.type === 'Tangent' && [c.first, c.second, c.third].includes(g1) && [c.first, c.second, c.third].includes(g2)) : undefined
        if (t) { if (t.first !== g1) [t.second, t.first] = [t.first, t.second]; t.firstPos = ps1 }
        else out.push(constraint('PointOnObject', g1, ps1, g2))
        return true
      }
      case 'Symmetric': out.push(constraint('Symmetric', g2, START, g2, END, geoId1, posId1)); return true
      case 'Horizontal': case 'Vertical': out.push(constraint(ac.type, g2 !== GEO_UNDEF ? g2 : geoId1)); return true
      case 'Perpendicular': case 'Parallel': out.push(constraint(ac.type, geoId1, NONE, g2)); return true
      case 'Tangent': {
        const geo = S.getGeometry()
        if (!geo[geoId1] || !geo[g2]) return false
        const coin = out.find((c) => c.type === 'Coincident' && c.first === geoId1 && c.second === g2)
        const poo = out.find((c) => c.type === 'PointOnObject' && [c.first, c.second].includes(geoId1) && [c.first, c.second].includes(g2))
        if (coin && startOrEnd(coin.firstPos) && startOrEnd(coin.secondPos)) coin.type = 'Tangent'
        else if (poo && startOrEnd(poo.firstPos)) poo.type = 'Tangent'
        else if (coin && coin.firstPos === MID && coin.secondPos === MID && SK.isCircular(geo[geoId1]) && SK.isCircular(geo[g2])) out.push(constraint('Equal', geoId1, NONE, g2))
        else out.push(constraint('Tangent', geoId1, NONE, g2))
        return true
      }
      default: return true
    }
  }
  /** filterRedundantAutoConstraints: what the solver calls redundant among the new constraints goes (a redundancy among
   *  the sketch's own is an error), and so does what conflicts. False when a redundancy is not an auto-constraint. */
  filterRedundant(autos: Constraint[]): boolean {
    if (!autos.length) return true
    const r = S.diagnoseWith(autos)
    if (!r) return true
    const last = S.getConstraints().length - 1
    if (r.redundant.length) {
      for (const k of [...r.redundant].sort((a, b) => b - a)) { if (k > last) autos.splice(k - last - 1, 1); else return false }
    }
    if (r.conflicting.length) for (const k of [...r.conflicting].sort((a, b) => b - a)) if (k > last) autos.splice(k - last - 1, 1)
    return true
  }
  /** DrawSketchHandler::createAutoConstraints: the old handlers' way (the point tool): each suggestion straight in. */
  createAutoConstraintsDirect(autos: AutoConstraint[], geoId1: number, posId1: PointPos) {
    if (!autos.length) return
    S.openCommand('Add Auto-Constraints')
    for (const c of autos) {
      let g1 = geoId1, p1 = posId1, g2 = c.geoId, p2 = c.posId
      switch (c.type) {
        case 'Coincident': if (p1 === NONE) continue; S.addConstraint(constraint('Coincident', g1, p1, g2, p2)); break
        case 'PointOnObject': if (p1 === NONE) { [g1, g2] = [g2, g1]; [p1, p2] = [p2, p1] } S.addConstraint(constraint('PointOnObject', g1, p1, g2)); break
        case 'Symmetric': S.addConstraint(constraint('Symmetric', g2, START, g2, END, g1, p1)); break
        case 'Horizontal': case 'Vertical': S.addConstraint(constraint(c.type, g2 !== GEO_UNDEF ? g2 : g1)); break
        case 'Perpendicular': case 'Parallel': case 'Tangent': S.addConstraint(constraint(c.type, g1, NONE, g2)); break
      }
      void p2
    }
    S.commitCommand()
  }
}

/** Utils.cpp removeRedundantHorizontalVertical: no horizontal or vertical when both ends are already tied to the
 *  external geometry, or one to the origin and the other on an axis. */
function removeRedundantHorizontalVertical(sug1: AutoConstraint[], sug2: AutoConstraint[]) {
  if (!sug1.length || !sug2.length) return
  const detect = (sug: AutoConstraint[]) => {
    let ext = false, orig = false, axis = false
    for (const c of sug) {
      if (c.type === 'Coincident' && !ext) {
        const co = SK.coincidentPoints(S.getConstraints(), c.geoId, c.posId)
        if (co.size) { ext = Math.min(...co.keys()) < 0; if (co.get(-1) === START) orig = true }
        else { ext = c.geoId < 0; orig = c.geoId === -1 && c.posId === START }
      } else if (c.type === 'PointOnObject' && !axis) axis = (c.geoId === -1 || c.geoId === -2) && c.posId === NONE
    }
    return { ext, orig, axis }
  }
  const a = detect(sug1), b = detect(sug2)
  if ((a.ext && b.ext) || (a.orig && b.axis) || (b.orig && a.axis)) {
    for (let i = sug2.length - 1; i >= 0; i--) if (sug2[i].type === 'Horizontal' || sug2[i].type === 'Vertical') sug2.splice(i, 1)
    for (let i = sug1.length - 1; i >= 0; i--) if (sug1[i].type === 'Horizontal' || sug1[i].type === 'Vertical') sug1.splice(i, 1)
  }
}

/** DrawSketchDefaultHandler + DrawSketchControllableHandler: a state machine of clicks, the shape built from them
 *  (ShapeGeometry, ShapeConstraints), the auto-constraints made at the end, continuous mode. */
export abstract class DefaultHandler extends DrawSketchHandler {
  protected state = 0
  /** The number of clicks (SelectModeT's states before End). */
  protected abstract readonly states: number
  protected method = 0
  protected readonly methods: number = 1
  protected sug: AutoConstraint[][] = [[], [], [], [], []]
  protected autos: Constraint[] = []
  protected shapeGeometry: Geo[] = []
  protected shapeConstraints: Constraint[] = []
  protected avoidRedundants = true
  /** Sketcher's ContinuousCreationMode (on). */
  protected continuousMode = true
  protected get isLast() { return this.state >= this.states }

  /** DrawSketchController's prevCursorPosition: where the cursor was last. */
  protected cursorPos: XY = [0, 0]
  activated() { this.applyMode() }
  /** mouseMove: the hints' snapping, then the state's update. */
  mouseMove(p: XY) {
    this.cursorPos = p
    const q = this.snapToTangentHint(p) ?? this.snapToParPerpHint(p) ?? p
    this.update(q)
  }
  pressButton(p: XY) {
    this.cursorPos = p
    const q = this.snapToTangentHint(p) ?? this.snapToParPerpHint(p) ?? p
    this.update(q)
    this.onButtonPressed(q)
    return true
  }
  releaseButton(_p: XY) { this.finish(); return true }
  registerPressedKey(pressed: boolean, key: string): boolean {
    if (key === 'M' && pressed && !this.isLast) { this.nextMethod(); return true }
    if (key === 'Escape' && pressed) { this.cancelCurrentAction(); return true }
    return key === 'Escape'
  }
  pressRightButton() { this.cancelCurrentAction() }
  cancelCurrentAction() { this.rightButtonOrEsc() }
  rightButtonOrEsc() { if (this.state === 0) this.quit(); else this.handleContinuousMode() }
  protected nextMethod() {
    if (this.methods <= 1) return
    this.method = (this.method + 1) % this.methods
    this.onMethodChanged()
    S.applyCursor(); S.updateHints()
    if (this.resetOnMethodChange()) this.reset()
    // DrawSketchController::onConstructionMethodChanged: the new method drawn at once, where the cursor was
    this.mouseMove(this.cursorPos)
  }
  protected onMethodChanged() {}
  protected resetOnMethodChange() { return true }
  protected canGoToNextMode() { return true }
  protected onButtonPressed(p: XY) {
    this.update(p)
    if (this.canGoToNextMode()) this.setState(this.state + 1)
  }
  protected setState(st: number) {
    this.state = st
    this.onModeChanged()
  }
  /** onModeChanged: the end makes the shape (finish); otherwise the new state is drawn at once. */
  protected onModeChanged() {
    S.setEdit({ positionText: null })
    S.updateHints()
    this.applyMode()
    if (!this.finish()) this.afterModeChanged()
  }
  protected applyMode() { this.angleSnappingControl() }
  protected afterModeChanged() {}
  protected angleSnappingControl() { S.setAngleSnapping(false) }
  /** finish: at the end, the commands, the auto-constraints, a solve, then continuous mode. */
  protected finish(): boolean {
    if (!this.isLast) return false
    S.setEdit({ positionText: null })
    try {
      this.executeCommands()
      this.generateAutoConstraints(); this.createAutoConstraints()
    } catch (e) { console.error(e) }
    S.solve()
    return this.handleContinuousMode()
  }
  protected handleContinuousMode(): boolean {
    if (this.continuousMode) { this.reset(); return false }
    S.purgeHandler()
    return true
  }
  reset() {
    S.setEdit({ curves: [], markers: [], positionText: null, extensionHint: null })
    this.resetParPerpHint()
    for (const s of this.sug) s.length = 0
    this.autos = []; this.shapeGeometry = []; this.shapeConstraints = []
    this.onReset()
    this.state = 0
    this.applyMode()
    this.cursorTail = []
    S.applyCursor(); S.updateHints()
  }
  protected onReset() {}
  protected abstract update(p: XY): void
  protected executeCommands() {}
  protected generateAutoConstraints() {}
  protected createAutoConstraints() { this.createGeneratedAutoConstraints(true) }
  /** generateAutoConstraintsOnElement. */
  protected onElement(sug: AutoConstraint[], geoId: number, pos: PointPos) {
    for (const ac of sug) if (!this.generateOne(ac, geoId, pos, this.autos)) return
  }
  protected removeRedundantAutoConstraints() {
    if (!this.filterRedundant(this.autos)) throw new Error('Redundant constraint is not an autoconstraint. No autoconstraints or additional constraints were added. Please report!')
  }
  protected createGeneratedAutoConstraints(own: boolean) {
    if (!this.autos.length) return
    if (own) S.openCommand('Add Auto-Constraints')
    S.addConstraint(this.autos)
    if (own) S.commitCommand()
    this.autos = []
  }
  /** commandAddShapeGeometryAndConstraints. */
  protected addShape() {
    S.addGeometry(this.shapeGeometry, undefined)
    if (this.shapeConstraints.length) S.addConstraint(this.shapeConstraints)
  }
  protected line(a: XY, b: XY, construction = this.isConstructionMode()): Geo { const g: Geo = { type: 'LineSegment', start: a, end: b }; return construction ? { ...g, construction: true } : g }
  protected arc(c: XY, start: number, end: number, r: number, construction = this.isConstructionMode()): Geo { return SK.normalArc(c, r, start, end, construction) }
  protected circle(c: XY, r: number, construction = this.isConstructionMode()): Geo { const g: Geo = { type: 'Circle', center: c, radius: r }; return construction ? { ...g, construction: true } : g }
  protected point(p: XY, construction = this.isConstructionMode()): Geo { const g: Geo = { type: 'Point', at: p }; return construction ? { ...g, construction: true } : g }
  protected shapeCon(type: ConstraintType, f: number, fp: PointPos = NONE, s = GEO_UNDEF, sp: PointPos = NONE, t = GEO_UNDEF, tp: PointPos = NONE) {
    this.shapeConstraints.push(constraint(type, f, fp, s, sp, t, tp))
  }
  /** CreateAndDrawShapeGeometry: the shape as it would be, drawn as the edit curve. */
  protected drawShape() {
    this.createShape(true)
    S.setEdit({ curves: this.shapeGeometry.map((g) => SK.polyline(g)), construction: this.isConstructionMode() })
  }
  protected createShape(_onlyOutline: boolean) {}
  protected drawPositionAtCursor(p: XY) { S.setEdit({ positionText: { at: p, text: S.positionString(p) } }) }
  /** drawDirectionAtCursor, drawDoubleAtCursor and drawWidthHeightAtCursor draw only when the on-view parameters are
   *  hidden (OnViewParameterVisibility 0; the default 1 shows the dimensional ones instead). */
  protected clearCursorText() { S.setEdit({ positionText: null }) }
  hint(message: string, keys: string[]) { return { message, keys } }
}
const LMB = 'LMB', RMB = 'RMB'

// ── Point (DrawSketchHandlerPoint.h) ─────────────────────────────────────────────────────────────────────────────
export class PointHandler extends DefaultHandler {
  readonly toolName = 'DSH_Point'
  protected readonly states = 1
  private editPoint: XY = [0, 0]
  crosshair() { return 'Sketcher_Pointer_Create_Point' }
  hints() { return [this.hint('%1 place a point', [LMB])] }
  protected update(p: XY) {
    if (this.state !== 0) return
    this.seekAndRender(this.sug[0], p, [0, 0])
    this.editPoint = this.lineExtensionSnapPoint() ?? p
    this.drawPositionAtCursor(this.editPoint)
  }
  protected executeCommands() {
    S.openCommand('Add sketch point')
    S.addGeometry(this.point(this.editPoint))
    S.commitCommand()
  }
  protected createAutoConstraints() {
    if (this.sug[0].length) { this.createAutoConstraintsDirect(this.sug[0], S.highestCurveIndex(), START); this.sug[0].length = 0 }
  }
}

// ── Line (DrawSketchHandlerLine.h) ───────────────────────────────────────────────────────────────────────────────
/** LineConstructionMethod: OnePointLengthAngle (the default), OnePointWidthHeight, TwoPoints. */
export class LineHandler extends DefaultHandler {
  readonly toolName = 'DSH_Line'
  protected readonly states = 2
  protected readonly methods = 3
  private startPoint: XY = [0, 0]
  private endPoint: XY = [0, 0]
  private length = 0
  crosshair() { return this.method === 0 ? 'Sketcher_Pointer_Create_Line_Polar' : 'Sketcher_Pointer_Create_Line' }
  hints() { return [this.hint(this.state === 0 ? '%1 pick first point' : '%1 pick second point', [LMB]), this.hint('%1 switch mode', ['M'])] }
  getStartPointOfCurrentSegment() { return this.state === 1 ? this.startPoint : null }
  protected update(p: XY) {
    if (this.state === 0) {
      this.seekAndRender(this.sug[0], p, [0, 0])
      this.startPoint = this.lineExtensionSnapPoint() ?? p
      this.drawPositionAtCursor(this.startPoint)
    } else if (this.state === 1) {
      this.seekAndRender(this.sug[1], p, sub(p, this.startPoint))
      this.endPoint = this.lineExtensionSnapPoint() ?? p
      this.drawShape()
    }
  }
  protected createShape() {
    this.shapeGeometry = []
    this.length = len(sub(this.endPoint, this.startPoint))
    if (this.length > CONFUSION) this.shapeGeometry.push(this.line(this.startPoint, this.endPoint))
  }
  protected canGoToNextMode() { return !(this.state === 1 && this.length < CONFUSION) }
  protected angleSnappingControl() { if (this.state === 1) S.setAngleSnapping(true, this.startPoint); else S.setAngleSnapping(false) }
  protected executeCommands() {
    this.createShape()
    S.openCommand('Add sketch line')
    this.addShape()
    S.commitCommand()
  }
  protected generateAutoConstraints() {
    const id = S.highestCurveIndex()
    if (this.avoidRedundants) removeRedundantHorizontalVertical(this.sug[0], this.sug[1])
    this.onElement(this.sug[0], id, START)
    this.onElement(this.sug[1], id, END)
    this.removeRedundantAutoConstraints()
  }
  protected createAutoConstraints() { this.createGeneratedAutoConstraints(true); this.sug[0].length = 0; this.sug[1].length = 0 }
}

// ── Polyline (DrawSketchHandlerPolyLine in DrawSketchHandlerLineSet.h) ──────────────────────────────────────────
/** PolyLineConstructionMethod: Line, Arc (M switches; the first segment is always a line). R takes back the last
 *  point, F toggles the fillet; Esc or the right button ends the polyline, a second Esc the tool. */
export class PolylineHandler extends DefaultHandler {
  readonly toolName = 'DSH_PolyLine'
  protected readonly states = 2
  protected readonly methods = 2
  private prevCursorPos: XY = [0, 0]
  private points: XY[] = []
  private geoEltIds: [number, PointPos][] = []
  private resetEdge = true
  private previousDirectionAngle = 0
  private dirChangeAngle = 0
  private angleToPrevious = 0
  private pos: PointPos = END
  private center: XY = [0, 0]
  crosshair() { return 'Sketcher_Pointer_Create_Lineset' }
  hints() {
    if (this.state === 0) return [this.hint('%1 pick first point', [LMB])]
    return [this.hint('%1 pick next point', [LMB]), this.hint('%1 finish', [RMB]), this.hint(this.method === 0 ? '%1 switch to arc' : '%1 switch to line', ['M']),
      this.hint('%1 toggle fillet', ['F']), this.hint('%1 undo last point', ['R'])]
  }
  activated() { super.activated(); S.openCommand('Add sketch polyline') }
  getStartPointOfCurrentSegment() { return this.method === 0 && this.state === 1 && this.points.length ? this.points[this.points.length - 1] : null }
  private last(): XY { return this.points.length ? this.points[this.points.length - 1] : [0, 0] }
  protected update(p: XY) {
    this.prevCursorPos = p
    if (this.state === 0) { this.drawPositionAtCursor(p); this.seekAndRender(this.sug[0], p, [0, 0]) }
    else if (this.state === 1) {
      const a1 = angleOf(sub(p, this.last())) - this.previousDirectionAngle, a2 = a1 + (a1 < 0 ? 2 : -2) * Math.PI
      this.dirChangeAngle = Math.abs(a1 - this.dirChangeAngle) < Math.abs(a2 - this.dirChangeAngle) ? a1 : a2
      this.drawShape()
      this.seekAndRender(this.sug[1], p, this.method === 0 ? sub(p, this.last()) : [0, 0])
    }
  }
  protected onMethodChanged() {
    // the first segment cannot be an arc
    if (this.method === 1) { if (!this.geoEltIds.length) { this.method = 0; return } this.resetEdge = true }
  }
  protected resetOnMethodChange() { return false }
  private previousDirection(): XY {
    if (this.points.length <= 1) return [1, 0]
    const [g, pos] = this.geoEltIds[this.geoEltIds.length - 1]
    const e = S.getGeometry()[g]
    if (!SK.isArc(e)) return normalize(sub(this.points[this.points.length - 2], this.points[this.points.length - 1]))
    let dir: XY
    if (pos === END) { const d = sub(S.getPoint(g, END)!, e.center); dir = [d[1], -d[0]] }
    else { const d = sub(S.getPoint(g, START)!, e.center); dir = [-d[1], d[0]] }
    return normalize(dir)
  }
  private currentInitialDirection(): XY {
    if (this.method === 0) return sub(this.prevCursorPos, this.last())
    const d = this.previousDirection(), a = this.angleToPrevious
    return [d[0] * Math.cos(a) - d[1] * Math.sin(a), d[0] * Math.sin(a) + d[1] * Math.cos(a)]
  }
  private arcCenter(p: XY): number {
    const lp = this.last(), t = this.currentInitialDirection()
    const theta = getAngle(t, sub(p, lp))
    let radius = len(sub(p, lp)) / (2 * Math.sin(theta))
    const [x1, y1] = lp, x2 = x1 + t[0], y2 = y1 + t[1], [x3, y3] = p
    if ((x2 * y3 - x3 * y2) - (x1 * y3 - x3 * y1) + (x1 * y2 - x2 * y1) > 0) radius *= -1
    if (!Number.isFinite(radius)) radius = 0
    this.center = add(lp, [radius * t[1], -radius * t[0]])
    return radius
  }
  protected createShape(onlyOutline: boolean) {
    this.shapeGeometry = []; this.shapeConstraints = []
    if (!this.points.length) return
    const lp = this.last(), cd = sub(this.prevCursorPos, lp)
    if (len(cd) < CONFUSION) { this.resetEdge = true; return }
    this.pos = END
    let posId: PointPos = START
    const prevDir = this.previousDirection()
    if (this.method === 0) this.shapeGeometry.push(this.line(lp, this.prevCursorPos))
    else {
      if (this.resetEdge) {
        this.resetEdge = false
        const sign = prevDir[0] * (this.prevCursorPos[1] - lp[1]) - prevDir[1] * (this.prevCursorPos[0] - lp[0]) > 0 ? 1 : -1
        this.angleToPrevious = sign * (getAngle(cd, prevDir) - Math.PI)
        this.angleToPrevious = Math.round(this.angleToPrevious / (Math.PI / 2)) * (Math.PI / 2)
      }
      const radius = this.arcCenter(this.prevCursorPos)
      if (radius === 0) return
      const rx = lp[0] - this.center[0], ry = lp[1] - this.center[1]
      const startAngle = Math.atan2(ry, rx)
      const rxe = this.prevCursorPos[0] - this.center[0], rye = this.prevCursorPos[1] - this.center[1]
      let range = Math.atan2(-rxe * ry + rye * rx, rxe * rx + rye * ry)
      if (!Number.isFinite(range)) range = 0
      if (radius >= 0 && range > 0) range -= 2 * Math.PI
      if (radius < 0 && range < 0) range += 2 * Math.PI
      let s = startAngle, e = startAngle + range
      if (radius < 0) { [s, e] = [e, s]; posId = END; this.pos = START }
      this.shapeGeometry.push(this.arc(this.center, s, e, Math.abs(radius)))
    }
    if (!onlyOutline && this.geoEltIds.length) {
      const [geoId, lastPos] = this.geoEltIds[this.geoEltIds.length - 1], geoId2 = S.highestCurveIndex() + 1
      if (this.method === 0) {
        const ac1 = this.sug[1], before = ac1.length
        for (let i = ac1.length - 1; i >= 0; i--) if (ac1[i].type === 'Tangent' && ac1[i].geoId === geoId && ac1[i].posId === lastPos) ac1.splice(i, 1)
        this.shapeCon(ac1.length !== before ? 'Tangent' : 'Coincident', geoId, lastPos, geoId2, posId)
      } else {
        const byPi = Math.round(this.angleToPrevious / Math.PI) * Math.PI, byHalf = Math.round(this.angleToPrevious / (Math.PI / 2)) * (Math.PI / 2)
        if (Math.abs(this.angleToPrevious - byPi) < CONFUSION) this.shapeCon('Tangent', geoId, lastPos, geoId2, posId)
        else if (Math.abs(this.angleToPrevious - byHalf) < CONFUSION) this.shapeCon('Perpendicular', geoId, lastPos, geoId2, posId)
      }
    }
  }
  protected canGoToNextMode() {
    if (this.state === 0) { this.points.push(this.prevCursorPos); return true }
    // each click adds a segment at once; the polyline stays in this state until it closes
    this.createShape(false)
    if (!this.shapeGeometry.length) return false
    this.resetParPerpHint()
    this.addShape()
    const geoId = S.highestCurveIndex()
    this.geoEltIds.push([geoId, this.pos])
    let closed = false
    const ac1Pos = this.pos
    if (this.geoEltIds.length === 1) this.onElement(this.sug[0], geoId, START)
    else {
      for (const ac of this.sug[1]) {
        if (ac.type !== 'Coincident' && ac.type !== 'Tangent') continue
        if (ac.geoId === this.geoEltIds[0][0] && ac.posId === START) { closed = true; continue }
        if (SK.coincidentPoints(S.getConstraints(), ac.geoId, ac.posId).get(this.geoEltIds[0][0]) === START) closed = true
      }
    }
    this.onElement(this.sug[1], geoId, ac1Pos)
    this.sug[1].length = 0
    this.removeRedundantAutoConstraints()
    this.createGeneratedAutoConstraints(false)
    this.sug[0].length = 0
    this.sug[1].length = 0
    S.solve()
    const [lg, lpos] = this.geoEltIds[this.geoEltIds.length - 1]
    this.points.push(S.getPoint(lg, lpos)!)
    this.previousDirectionAngle = angleOf(this.previousDirection())
    if (!closed) {
      S.setAngleSnapping(true, this.last())
      this.resetEdge = true
      this.update(this.prevCursorPos)
    }
    return closed
  }
  protected angleSnappingControl() { if (this.state === 1) S.setAngleSnapping(true, this.last()); else S.setAngleSnapping(false) }
  protected executeCommands() { S.commitCommand() }
  protected generateAutoConstraints() { this.removeRedundantAutoConstraints() }
  protected createAutoConstraints() {}
  quit() {
    if (this.state !== 1) { S.abortCommand(); super.quit(); return }
    if (!this.geoEltIds.length) { this.handleContinuousMode(); return }
    this.setState(2)
  }
  rightButtonOrEsc() { this.quit() }
  registerPressedKey(pressed: boolean, key: string): boolean {
    if (key === 'R' && !pressed && this.state === 1) { this.undoLastPoint(); return true }
    return super.registerPressedKey(pressed, key)
  }
  private undoLastPoint() {
    if (!this.geoEltIds.length) { this.quit(); return }
    const [del] = this.geoEltIds.pop()!
    this.points.pop()
    S.delGeometries([del])
    S.solve()
    this.previousDirectionAngle = angleOf(this.previousDirection())
    S.setAngleSnapping(true, this.last())
    this.update(this.prevCursorPos)
  }
  protected onReset() {
    S.abortCommand()
    S.openCommand('Add sketch polyline')
    this.geoEltIds = []; this.points = []
    this.previousDirectionAngle = 0; this.dirChangeAngle = 0; this.angleToPrevious = 0; this.pos = END
    this.method = 0
  }
  deactivated() { super.deactivated(); S.abortCommand() }
}

// ── Arc (DrawSketchHandlerArc.h) ─────────────────────────────────────────────────────────────────────────────────
/** CircleEllipseConstructionMethod: Center (centre, start, end) and ThreeRim (two ends, then a point on the arc). */
export class ArcHandler extends DefaultHandler {
  readonly toolName = 'DSH_Arc'
  protected readonly states = 3
  protected readonly methods = 2
  private centerPoint: XY = [0, 0]; private firstPoint: XY = [0, 0]; private secondPoint: XY = [0, 0]
  private radius = 0; private startAngle = 0; private endAngle = 0; private arcAngle = 0
  private arcPos1: PointPos = NONE; private arcPos2: PointPos = NONE
  constructor(method = 0) { super(); this.method = method }
  crosshair() { return this.method === 0 ? 'Sketcher_Pointer_Create_Arc' : 'Sketcher_Pointer_Create_3PointArc' }
  hints() {
    const c = ['%1 pick arc center', '%1 pick arc start point', '%1 pick arc end point'], r = ['%1 pick first arc point', '%1 pick second arc point', '%1 pick third arc point']
    return [this.hint((this.method === 0 ? c : r)[Math.min(this.state, 2)], [LMB]), this.hint('%1 switch mode', ['M'])]
  }
  protected update(p: XY) {
    if (this.state === 0) {
      this.drawPositionAtCursor(p)
      if (this.method === 0) this.centerPoint = p; else this.firstPoint = p
      this.seekAndRender(this.sug[0], p, [0, 0])
    } else if (this.state === 1) {
      if (this.method === 0) { this.firstPoint = p; this.startAngle = angleOf(sub(this.firstPoint, this.centerPoint)) }
      else { this.centerPoint = add(mul(sub(p, this.firstPoint), 0.5), this.firstPoint); this.secondPoint = p }
      this.radius = len(sub(p, this.centerPoint))
      this.drawShape()
      if (this.method === 0) this.clearCursorText(); else this.drawPositionAtCursor(p)
      this.seekAndRender(this.sug[1], p, [0, 0])
    } else if (this.state === 2) {
      const backup = this.startAngle
      if (this.method === 0) {
        this.secondPoint = p
        const a1 = angleOf(sub(p, this.centerPoint)) - this.startAngle, a2 = a1 + (a1 < 0 ? 2 : -2) * Math.PI
        this.arcAngle = Math.abs(a1 - this.arcAngle) < Math.abs(a2 - this.arcAngle) ? a1 : a2
        if (this.arcAngle > 0) this.endAngle = this.startAngle + this.arcAngle
        else { this.endAngle = this.startAngle; this.startAngle = this.startAngle + this.arcAngle }
      } else {
        if (areCollinear(this.firstPoint, this.secondPoint, p)) return
        this.centerPoint = circleCenter(this.firstPoint, this.secondPoint, p)
        this.radius = len(sub(p, this.centerPoint))
        const a1 = angleOf(sub(this.firstPoint, this.centerPoint)), a2 = angleOf(sub(this.secondPoint, this.centerPoint)), a3 = angleOf(sub(p, this.centerPoint))
        if (a3 > Math.min(a1, a2) && a3 < Math.max(a1, a2)) {
          [this.arcPos1, this.arcPos2] = a2 > a1 ? [START, END] : [END, START]
          this.startAngle = Math.min(a1, a2); this.endAngle = Math.max(a1, a2); this.arcAngle = this.endAngle - this.startAngle
        } else {
          [this.arcPos1, this.arcPos2] = a2 > a1 ? [END, START] : [START, END]
          this.startAngle = Math.max(a1, a2); this.endAngle = Math.min(a1, a2); this.arcAngle = 2 * Math.PI - (this.startAngle - this.endAngle)
        }
      }
      this.drawShape()
      if (this.method === 0) { this.startAngle = backup; this.clearCursorText(); this.seekAndRender(this.sug[2], p, [0, 0]) }
      else { this.drawPositionAtCursor(p); this.seekAndRender(this.sug[2], p, [0, 0], 'curve') }
    }
  }
  protected createShape(onlyOutline: boolean) {
    this.shapeGeometry = []
    if (this.radius < CONFUSION) return
    if (this.state === 1) this.shapeGeometry.push(this.circle(this.centerPoint, this.radius))
    else {
      if (Math.abs(this.arcAngle) < CONFUSION) return
      this.shapeGeometry.push(this.arc(this.centerPoint, this.startAngle, this.endAngle > this.startAngle ? this.endAngle : this.endAngle + 2 * Math.PI, this.radius))
    }
    if (onlyOutline) {
      const k = 0.8, c = this.centerPoint
      if (this.method === 0 && this.state === 2) {
        this.shapeGeometry.push(this.line(c, add(c, [Math.cos(this.startAngle) * k * this.radius, Math.sin(this.startAngle) * k * this.radius])),
          this.line(c, add(c, [Math.cos(this.endAngle) * k * this.radius, Math.sin(this.endAngle) * k * this.radius])))
      } else if (this.method === 1 && this.state === 1) this.shapeGeometry.push(this.line(this.firstPoint, this.secondPoint))
      else if (this.method === 1 && this.state === 2) this.shapeGeometry.push(this.line(c, add(c, mul(sub(this.secondPoint, c), k))), this.line(c, add(c, mul(sub(this.firstPoint, c), k))))
    }
  }
  protected canGoToNextMode() { return !((this.state === 1 && this.radius < CONFUSION) || (this.state === 2 && Math.abs(this.arcAngle) < CONFUSION)) }
  protected angleSnappingControl() { if (this.method === 0 && (this.state === 1 || this.state === 2)) S.setAngleSnapping(true, this.centerPoint); else S.setAngleSnapping(false) }
  protected executeCommands() {
    if (this.method === 0) { if (this.arcAngle > 0) this.endAngle = this.startAngle + this.arcAngle; else { this.endAngle = this.startAngle; this.startAngle += this.arcAngle } }
    this.createShape(false)
    S.openCommand('Add sketch arc')
    this.addShape()
    S.commitCommand()
  }
  protected generateAutoConstraints() {
    const id = S.highestCurveIndex(), [ac1, ac2, ac3] = this.sug
    if (this.method === 0) {
      for (const c of ac1) {
        if (c.type !== 'Symmetric') continue
        const coincidentToEnd = (ac: AutoConstraint) => ac.type === 'Coincident' && [START, END].some((p) => ac.geoId === c.geoId ? ac.posId === p : SK.coincidentPoints(S.getConstraints(), ac.geoId, ac.posId).get(c.geoId) === p)
        if (ac2.some(coincidentToEnd) && ac3.some(coincidentToEnd)) c.type = 'PointOnObject'
      }
      this.onElement(ac1, id, MID)
      this.onElement(ac2, id, this.arcAngle > 0 ? START : END)
      this.onElement(ac3, id, this.arcAngle > 0 ? END : START)
    } else {
      this.onElement(ac1, id, this.arcPos1)
      this.onElement(ac2, id, this.arcPos2)
      this.onElement(ac3, id, NONE)
    }
    this.removeRedundantAutoConstraints()
  }
}

// ── Circle (DrawSketchHandlerCircle.h) ───────────────────────────────────────────────────────────────────────────
export class CircleHandler extends DefaultHandler {
  readonly toolName = 'DSH_Circle'
  protected readonly states = 3
  protected readonly methods = 2
  private centerPoint: XY = [0, 0]; private firstPoint: XY = [0, 0]; private secondPoint: XY = [0, 0]; private radius = 0
  constructor(method = 0) { super(); this.method = method }
  crosshair() { return this.method === 0 ? 'Sketcher_Pointer_Create_Circle' : 'Sketcher_Pointer_Create_3PointCircle' }
  hints() {
    const c = ['%1 pick circle center', '%1 pick rim point'], r = ['%1 pick first rim point', '%1 pick second rim point', '%1 pick third rim point']
    return [this.hint((this.method === 0 ? c : r)[Math.min(this.state, this.method === 0 ? 1 : 2)], [LMB]), this.hint('%1 switch mode', ['M'])]
  }
  protected update(p: XY) {
    if (this.state === 0) {
      this.drawPositionAtCursor(p)
      if (this.method === 0) { this.centerPoint = p; this.seekAndRender(this.sug[0], p, [0, 0]) }
      else { this.firstPoint = p; this.seekAndRender(this.sug[0], p, [0, 0], 'curve') }
    } else if (this.state === 1) {
      if (this.method === 1) this.centerPoint = add(mul(sub(p, this.firstPoint), 0.5), this.firstPoint)
      this.secondPoint = p
      this.radius = len(sub(p, this.centerPoint))
      this.drawShape()
      if (this.method === 0) this.clearCursorText(); else this.drawPositionAtCursor(p)
      this.seekAndRender(this.sug[1], p, this.method === 0 ? sub(p, this.centerPoint) : [0, 0], 'curve')
    } else if (this.state === 2) {
      if (areCollinear(this.firstPoint, this.secondPoint, p)) return
      this.centerPoint = circleCenter(this.firstPoint, this.secondPoint, p)
      this.radius = len(sub(p, this.centerPoint))
      this.drawPositionAtCursor(p)
      this.drawShape()
      this.seekAndRender(this.sug[2], p, [0, 0], 'curve')
    }
  }
  protected createShape() { this.shapeGeometry = this.radius < CONFUSION ? [] : [this.circle(this.centerPoint, this.radius)] }
  protected canGoToNextMode() { return !(this.state === 1 && this.radius < CONFUSION) }
  protected onButtonPressed(p: XY) {
    this.update(p)
    if (!this.canGoToNextMode()) return
    if (this.state === 1 && this.method === 0) this.setState(3)
    else this.setState(this.state + 1)
  }
  protected executeCommands() { this.createShape(); S.openCommand('Add sketch circle'); this.addShape(); S.commitCommand() }
  protected generateAutoConstraints() {
    const id = S.highestCurveIndex()
    if (this.method === 0) { this.onElement(this.sug[0], id, MID); this.onElement(this.sug[1], id, NONE) }
    else for (const s of this.sug.slice(0, 3)) this.onElement(s, id, NONE)
    this.removeRedundantAutoConstraints()
  }
}

// ── Rectangle (DrawSketchHandlerRectangle.h), Diagonal and CenterAndCorner, with rounded corners ────────────────
export class RectangleHandler extends DefaultHandler {
  readonly toolName = 'DSH_Rectangle'
  protected readonly states = 3
  protected readonly methods = 2
  private center: XY = [0, 0]; private c1: XY = [0, 0]; private c2: XY = [0, 0]; private c3: XY = [0, 0]; private c4: XY = [0, 0]
  private radius = 0; private length = 0; private width = 0; private angle = 0
  private angle123 = Math.PI / 2; private angle412 = Math.PI / 2
  private firstCurve = 0; private pointOneId = 0; private pointTwoId = 0; private centerPointId = 0
  constructor(method = 0, private roundCorners = false) { super() ; this.method = method }
  crosshair() {
    if (this.roundCorners) return this.method === 1 ? 'Sketcher_Pointer_Oblong_Center' : 'Sketcher_Pointer_Oblong'
    return this.method === 1 ? 'Sketcher_Pointer_Create_Box_Center' : 'Sketcher_Pointer_Create_Box'
  }
  hints() {
    const first = this.method === 1 ? '%1 pick center' : '%1 pick first corner', second = this.method === 1 ? '%1 pick corner' : '%1 pick opposite corner'
    return [this.hint([first, second, '%1 set corner radius'][Math.min(this.state, 2)], [LMB]), this.hint('%1 switch mode', ['M'])]
  }
  protected update(p: XY) {
    if (this.state === 0) {
      this.drawPositionAtCursor(p)
      if (this.method === 0) this.c1 = p; else this.center = p
      this.seekAndRender(this.sug[0], p, [0, 0])
    } else if (this.state === 1) {
      if (this.method === 1) this.c1 = sub(this.center, sub(p, this.center))
      this.c3 = p
      if (Math.sign(this.c3[0] - this.c1[0]) * Math.sign(this.c3[1] - this.c1[1]) > 0) { this.c2 = [p[0], this.c1[1]]; this.c4 = [this.c1[0], p[1]] }
      else { this.c4 = [p[0], this.c1[1]]; this.c2 = [this.c1[0], p[1]] }
      this.angle123 = this.angle412 = Math.PI / 2
      if (this.roundCorners) { this.length = len(sub(this.c2, this.c1)); this.width = len(sub(this.c4, this.c1)); this.radius = Math.min(this.length, this.width) / 6 }
      else this.radius = 0
      this.clearCursorText()
      this.drawShape()
      this.seekAndRender(this.sug[1], p, [0, 0])
    } else if (this.state === 2) {
      this.calculateRadius(p)
      this.clearCursorText()
      this.drawShape()
    }
  }
  private metrics(): boolean {
    const vl = sub(this.c2, this.c1), vw = sub(this.c4, this.c1)
    this.length = len(vl); this.width = len(vw); this.angle = angleOf(vl)
    return this.length >= CONFUSION && this.width >= CONFUSION
  }
  private calculateRadius(p: XY) {
    const u = normalize(sub(this.c2, this.c1)), v = normalize(sub(this.c4, this.c1)), e = sub(p, this.c1)
    const det = u[0] * v[1] - u[1] * v[0]
    let du = (v[1] * e[0] - v[0] * e[1]) / det, dv = (-u[1] * e[0] + u[0] * e[1]) / det
    if (-CONFUSION < du && du < 0) du = 0
    if (-CONFUSION < dv && dv < 0) dv = 0
    if (du < 0 || du > this.length || dv < 0 || dv > this.width) { this.radius = 0; return }
    const f = (a: number, b: number, ang: number) => (a + b + Math.max(2 * Math.sqrt(a * b) * Math.sin(ang / 2), -2 * Math.sqrt(a * b) * Math.sin(ang / 2))) * Math.tan(ang / 2)
    if (du < this.length - du && dv < this.width - dv) this.radius = f(du, dv, this.angle412)
    else if (du > this.length - du && dv < this.width - dv) this.radius = f(this.length - du, dv, this.angle123)
    else if (du < this.length - du && dv > this.width - dv) this.radius = f(du, this.width - dv, this.angle123)
    else this.radius = f(this.length - du, this.width - dv, this.angle412)
    const c412 = Math.cos(this.angle412 / 2), c123 = Math.cos(this.angle123 / 2)
    this.radius = Math.min(this.radius, Math.min(this.length * 0.999, this.width * 0.999) / (c412 / Math.sqrt(1 - c412 * c412) + c123 / Math.sqrt(1 - c123 * c123)))
  }
  protected createShape(onlyOutline: boolean) {
    this.shapeGeometry = []
    if (!this.metrics()) return
    const vl = mul(sub(this.c2, this.c1), 1 / this.length), vw = mul(sub(this.c4, this.c1), 1 / this.width)
    let L1 = this.radius, L2 = this.radius
    const c123 = Math.cos(this.angle123 / 2), c412 = Math.cos(this.angle412 / 2)
    if (c123 !== 1 && c412 !== 1) { L1 = this.radius / Math.sqrt(1 - c123 * c123); L2 = this.radius / Math.sqrt(1 - c412 * c412) }
    this.shapeGeometry.push(
      this.line(add(this.c1, mul(vl, L2 * c412)), sub(this.c2, mul(vl, L1 * c123))),
      this.line(add(this.c2, mul(vw, L1 * c123)), sub(this.c3, mul(vw, L2 * c412))),
      this.line(sub(this.c3, mul(vl, L2 * c412)), add(this.c4, mul(vl, L1 * c123))),
      this.line(sub(this.c4, mul(vw, L1 * c123)), add(this.c1, mul(vw, L2 * c412))))
    if (this.roundCorners && this.radius > CONFUSION) {
      const end = this.angle - Math.PI / 2, b1 = normalize(add(vl, vw)), b2 = normalize(sub(vl, vw))
      const r = this.radius
      this.shapeGeometry.push(
        this.arc(add(this.c1, mul(b1, L2)), end - Math.PI + this.angle412, end, r),
        this.arc(sub(this.c2, mul(b2, L1)), end, end - Math.PI - this.angle123, r),
        this.arc(sub(this.c3, mul(b1, L2)), end + this.angle412, end - Math.PI, r),
        this.arc(add(this.c4, mul(b2, L1)), end - Math.PI, end - this.angle123, r))
    }
    if (onlyOutline) return
    this.shapeConstraints = []
    const fc = this.firstCurve
    // addAlignmentConstraints: which sides are horizontal depends on which way the diagonal runs
    const [ta, tb]: ConstraintType[] = Math.sign(this.c3[0] - this.c1[0]) * Math.sign(this.c3[1] - this.c1[1]) < 0 ? ['Vertical', 'Horizontal'] : ['Horizontal', 'Vertical']
    const alignment = () => { this.shapeCon(ta, fc); this.shapeCon(ta, fc + 2); this.shapeCon(tb, fc + 1); this.shapeCon(tb, fc + 3) }
    if (this.radius > CONFUSION) { // finishOblongCreation
      const tan = (a: number, ap: PointPos, b: number, bp: PointPos) => this.shapeCon('Tangent', a, ap, b, bp)
      tan(fc, START, fc + 4, END); tan(fc, END, fc + 5, START); tan(fc + 1, START, fc + 5, END); tan(fc + 1, END, fc + 6, START)
      tan(fc + 2, START, fc + 6, END); tan(fc + 2, END, fc + 7, START); tan(fc + 3, START, fc + 7, END); tan(fc + 3, END, fc + 4, START)
      alignment()
      this.shapeCon('Equal', fc + 4, NONE, fc + 5); this.shapeCon('Equal', fc + 5, NONE, fc + 6); this.shapeCon('Equal', fc + 6, NONE, fc + 7)
      if (this.method === 1) { // finishOblongCenterAndCorner
        this.pointOneId = fc + 8; this.centerPointId = fc + 9
        this.shapeGeometry.push(this.point(this.c3, true), this.point(this.center, true))
        this.shapeCon('Symmetric', fc + 2, START, fc, START, this.centerPointId, START)
        this.shapeCon('PointOnObject', this.pointOneId, START, fc + 1); this.shapeCon('PointOnObject', this.pointOneId, START, fc + 2)
      } else { // finishOblongDiagonal
        this.pointOneId = fc + 8; this.pointTwoId = fc + 9
        this.shapeGeometry.push(this.point(this.c1, true), this.point(this.c3, true))
        this.shapeCon('PointOnObject', this.pointOneId, START, fc); this.shapeCon('PointOnObject', this.pointOneId, START, fc + 3)
        this.shapeCon('PointOnObject', this.pointTwoId, START, fc + 1); this.shapeCon('PointOnObject', this.pointTwoId, START, fc + 2)
      }
    } else { // finishRectangleCreation
      for (let k = 0; k < 4; k++) this.shapeCon('Coincident', fc + k, END, fc + ((k + 1) % 4), START)
      alignment()
      if (this.method === 1) { // finishCenteredRectangleCreation
        this.centerPointId = fc + 4
        this.shapeGeometry.push(this.point(this.center, true))
        this.shapeCon('Symmetric', fc + 2, START, fc, START, this.centerPointId, START)
      }
    }
  }
  protected canGoToNextMode() { return !(this.state === 1 && !this.metrics()) }
  protected onButtonPressed(p: XY) {
    this.update(p)
    if (!this.canGoToNextMode()) return
    if (this.state === 1 && !this.roundCorners) this.setState(3)
    else if (this.state === 2) this.setState(3)
    else this.setState(this.state + 1)
  }
  protected executeCommands() {
    this.firstCurve = S.highestCurveIndex() + 1
    this.createShape(false)
    if (!this.shapeGeometry.length) throw new Error('Cannot create a rectangle with zero length or width')
    S.openCommand('Add sketch box')
    this.addShape()
    S.commitCommand()
  }
  protected generateAutoConstraints() {
    const fc = this.firstCurve, rounded = this.radius > CONFUSION
    if (this.method === 0) {
      if (rounded) { this.onElement(this.sug[0], this.pointOneId, START); this.onElement(this.sug[1], this.pointTwoId, START) }
      else { this.onElement(this.sug[0], fc, START); this.onElement(this.sug[1], fc + 1, END) }
    } else {
      this.onElement(this.sug[0], this.centerPointId, START)
      if (rounded) this.onElement(this.sug[1], this.pointOneId, START); else this.onElement(this.sug[1], fc + 1, END)
    }
    this.removeRedundantAutoConstraints()
  }
}

// ── Slot (DrawSketchHandlerSlot.h) ───────────────────────────────────────────────────────────────────────────────
export class SlotHandler extends DefaultHandler {
  readonly toolName = 'DSH_Slot'
  protected readonly states = 3
  private startPoint: XY = [0, 0]; private secondPoint: XY = [0, 0]; private radius = 0; private length = 0; private angle = 0; private firstCurve = 0
  crosshair() { return 'Sketcher_Pointer_Slot' }
  hints() { return [this.hint(['%1 pick slot start point', '%1 pick slot end point', '%1 pick slot width'][Math.min(this.state, 2)], [LMB])] }
  protected update(p: XY) {
    if (this.state === 0) { this.drawPositionAtCursor(p); this.startPoint = p; this.seekAndRender(this.sug[0], p, [0, 0]) }
    else if (this.state === 1) {
      this.clearCursorText()
      this.secondPoint = p
      this.angle = angleOf(sub(this.secondPoint, this.startPoint)); this.length = len(sub(this.secondPoint, this.startPoint))
      this.radius = this.length * 0.2
      this.drawShape()
      this.seekAndRender(this.sug[1], p, sub(this.secondPoint, this.startPoint), 'vertexNoTangency')
    } else if (this.state === 2) {
      const L1 = len(sub(p, this.startPoint)), L2 = len(sub(p, this.secondPoint)), l = this.length
      if (L1 * L1 + l * l > L2 * L2 && L2 * L2 + l * l > L1 * L1) {
        const [s, e] = [this.startPoint, this.secondPoint]
        this.radius = Math.abs((e[1] - s[1]) * p[0] - (e[0] - s[0]) * p[1] + e[0] * s[1] - e[1] * s[0]) / l
      } else this.radius = Math.min(L1, L2)
      this.drawShape()
    }
  }
  protected createShape(onlyOutline: boolean) {
    this.shapeGeometry = []; this.shapeConstraints = []
    if (this.length < CONFUSION || this.radius < CONFUSION) return
    const a1 = this.arc(this.startPoint, Math.PI / 2 + this.angle, 1.5 * Math.PI + this.angle, this.radius)
    const a2 = this.arc(this.secondPoint, 1.5 * Math.PI + this.angle, Math.PI / 2 + this.angle + 2 * Math.PI, this.radius)
    const p = (g: Geo, pos: PointPos) => SK.getPoint([g], 0, pos)!
    this.shapeGeometry.push(a1, a2, this.line(p(a1, START), p(a2, END)), this.line(p(a1, END), p(a2, START)))
    if (onlyOutline) return
    const fc = this.firstCurve
    this.shapeCon('Tangent', fc, START, fc + 2, START); this.shapeCon('Tangent', fc, END, fc + 3, START)
    this.shapeCon('Tangent', fc + 1, END, fc + 2, END); this.shapeCon('Tangent', fc + 1, START, fc + 3, END)
    this.shapeCon('Equal', fc, NONE, fc + 1)
  }
  protected canGoToNextMode() { return !((this.state === 1 && this.length < CONFUSION) || (this.state === 2 && (this.length < CONFUSION || this.radius < CONFUSION))) }
  protected angleSnappingControl() { if (this.state === 1) S.setAngleSnapping(true, this.startPoint); else S.setAngleSnapping(false) }
  protected executeCommands() { this.firstCurve = S.highestCurveIndex() + 1; this.createShape(false); S.openCommand('Add slot'); this.addShape(); S.commitCommand() }
  protected generateAutoConstraints() {
    let alignment = false
    for (const ac of this.sug[1]) if (['Horizontal', 'Vertical', 'Perpendicular', 'Parallel'].includes(ac.type)) { ac.geoId = this.firstCurve + 2; alignment = true }
    if (this.avoidRedundants && alignment) removeRedundantHorizontalVertical(this.sug[0], this.sug[1])
    this.onElement(this.sug[0], S.highestCurveIndex() - 3, MID)
    this.onElement(this.sug[1], S.highestCurveIndex() - 2, MID)
    this.removeRedundantAutoConstraints()
  }
}

// ── Regular polygon (DrawSketchHandlerPolygon.h) ─────────────────────────────────────────────────────────────
export class PolygonHandler extends DefaultHandler {
  readonly toolName = 'DSH_Polygon'
  protected readonly states = 2
  private centerPoint: XY = [0, 0]; private firstCorner: XY = [0, 0]; private radius = 0
  constructor(private corners = 6) { super() }
  crosshair() { return 'Sketcher_Pointer_Regular_Polygon' }
  hints() {
    return this.state === 0 ? [this.hint('%1 pick polygon center', [LMB]), this.hint('%1/%2 increase/decrease number of sides', ['U', 'J'])]
      : [this.hint('%1 confirm', [LMB]), this.hint('%1/%2 increase/decrease number of sides', ['U', 'J'])]
  }
  registerPressedKey(pressed: boolean, key: string): boolean {
    if (!pressed && (key === 'U' || key === 'J')) { this.corners = Math.max(3, this.corners + (key === 'U' ? 1 : -1)); if (this.state === 1) this.drawShape(); return true }
    return super.registerPressedKey(pressed, key)
  }
  protected update(p: XY) {
    if (this.state === 0) { this.drawPositionAtCursor(p); this.centerPoint = p; this.seekAndRender(this.sug[0], p, [0, 0]) }
    else if (this.state === 1) { this.clearCursorText(); this.firstCorner = p; this.drawShape(); this.seekAndRender(this.sug[1], p, [0, 0]) }
  }
  protected createShape() {
    this.shapeGeometry = []
    const dv = sub(this.firstCorner, this.centerPoint)
    this.radius = len(dv)
    if (this.radius < CONFUSION) return
    const pts = Array.from({ length: this.corners }, (_, i): XY => {
      const a = (2 * Math.PI * i) / this.corners, c = Math.cos(a), s = Math.sin(a)
      return add(this.centerPoint, [c * dv[0] - s * dv[1], c * dv[1] + s * dv[0]])
    })
    for (let i = 0; i < this.corners; i++) this.shapeGeometry.push(this.line(pts[i], pts[(i + 1) % this.corners]))
  }
  protected canGoToNextMode() { return !(this.state === 1 && this.radius < CONFUSION) }
  protected angleSnappingControl() { if (this.state === 1) S.setAngleSnapping(true, this.centerPoint); else S.setAngleSnapping(false) }
  protected executeCommands() {
    this.createShape()
    S.openCommand('Add hexagon')
    const n = this.corners, first = S.addGeometry(this.shapeGeometry) - n + 1
    S.addGeometry(this.circle(this.centerPoint, this.radius, true))
    const circle = first + n, cons: Constraint[] = []
    for (let i = 0; i < n; i++) cons.push(constraint('Coincident', first + i, END, first + ((i + 1) % n), START))
    for (let i = 1; i < n; i++) cons.push(constraint('Equal', first, NONE, first + i))
    for (let i = 0; i < n; i++) cons.push(constraint('PointOnObject', first + i, END, circle))
    S.addConstraint(cons)
    S.commitCommand()
  }
  protected generateAutoConstraints() {
    const geo = S.getGeometry()
    for (let g = geo.length - 1; g >= 0; g--) {
      if (geo[g].type !== 'Circle') continue
      if (this.sug[0].length) this.onElement(this.sug[0], g, MID)
      if (this.sug[1].length) this.onElement(this.sug[1], g - 1, END)
      this.removeRedundantAutoConstraints()
      return
    }
  }
}

/** Sketcher_ToggleConstruction (CmdSketcherToggleConstruction): with geometry selected, each one toggled; without, the
 *  creation mode, and the running tool's cursor with it. */
export function toggleConstruction() {
  const curves = [...S.selectedCurves()].filter((g) => g >= 0)
  if (!curves.length) { S.setConstructionMode(!S.isConstructionMode()); S.applyCursor(); return }
  S.openCommand('Toggle draft from/to draft')
  for (const g of curves) S.toggleConstruction(g)
  S.commitCommand()
  S.clearSelection()
  S.solve()
}
