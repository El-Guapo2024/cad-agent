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
//   src/Mod/Sketcher/Gui/DrawSketchHandlerArcSlot.h: 2023 Ondsel
//   src/Mod/Sketcher/Gui/DrawSketchHandlerPolygon.h: 2022 Abdullah Tahiri
//   src/Mod/Sketcher/ProfileLib/RegularPolygon.py: 2014 Johan Kristensen, Juergen Riegel
//   src/Mod/Sketcher/Gui/Utils.cpp: 2021 Abdullah Tahiri
// The Sketcher's geometry tools: DrawSketchHandler (what an auto-constraint the cursor suggests, its cursor icons,
// how a suggestion becomes a constraint, redundant ones dropped), DrawSketchDefaultHandler's state machine (each click
// the next state, continuous mode, Esc and the right button, M for the next construction method), and the handlers:
// point, line, polyline, arc, circle, rectangle (four construction methods, rounded, framed), slot, arc slot and
// regular polygon, each making the
// geometry and constraints FreeCAD's makes for the same clicks.
import type { Geo, XY } from './solver'
import * as SK from './sketch'
import { type Constraint, type ConstraintType, type PointPos, NONE, START, END, MID, GEO_UNDEF, H_AXIS, V_AXIS, RT_PNT, constraint } from './sketch'
import * as S from './sketcher'
import { Controller, OVP, sketcherParam, ovpVisibilityPref, f6, constraintToAttachment, constraintLineByAngle, constraint2LinesByAngle, ensureViewFocus, RT_PNT_ID, V_AXIS_ID, H_AXIS_ID, type OvpSpec, type OvpTool } from './sketchovp'
import * as OPS from './sketchops'
import { report } from './store'

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
 *  (ShapeGeometry, ShapeConstraints), the auto-constraints made at the end, continuous mode; and the controller
 *  (sketchovp.ts) of the tool's on-view parameters and Tool Parameters box, whose specialisations a tool overrides
 *  (ovpSpec, ovpState, configureToolWidget, doEnforceControlParameters, adaptParameters, …). A tool that has none keeps
 *  the defaults, and then the controller does nothing. */
export abstract class DefaultHandler extends DrawSketchHandler implements OvpTool {
  protected state = 0
  /** The number of clicks (SelectModeT's states before End). */
  protected abstract readonly states: number
  protected method = 0
  protected readonly methods: number = 1
  protected sug: AutoConstraint[][] = [[], [], [], [], []]
  /** PAutoConstraintSize: no auto-constraints at all when 0 (finish leaves them out). */
  protected readonly autoConstraintSize: number = 5
  protected autos: Constraint[] = []
  protected shapeGeometry: Geo[] = []
  protected shapeConstraints: Constraint[] = []
  protected avoidRedundants = true
  /** Sketcher's ContinuousCreationMode (on). */
  continuousMode = true
  protected get isLast() { return this.state >= this.states }
  private nextMode: number | null = null
  /** The tool's controller (toolWidgetManager). */
  readonly ctl: Controller = new Controller(this)

  /** DrawSketchController's prevCursorPosition: where the cursor was last. */
  protected cursorPos: XY = [0, 0]
  /** DrawSketchHandler::activate: the controls made (TaskSketcherTool's toolChanged), then activated(). */
  activated() {
    this.ctl.initControls()
    this.continuousMode = sketcherParam<boolean>('Mod/Sketcher/ContinuousCreationMode')
    this.applyMode()
  }
  deactivated() { this.ctl.dispose(); super.deactivated() }
  /** DrawSketchControllableHandler::mouseMove: the hints' snapping, the parameters set enforced, the state's update,
   *  then the parameters follow the cursor. */
  mouseMove(p: XY) {
    this.cursorPos = p
    const q = this.snapToTangentHint(p) ?? this.snapToParPerpHint(p) ?? p
    this.ctl.mouseMoved(q)
    const e = this.ctl.enforceControlParameters(q)
    if (!e) return
    this.update(e)
    this.ctl.adaptParameters(e)
  }
  pressButton(p: XY) {
    this.cursorPos = p
    const q = this.snapToTangentHint(p) ?? this.snapToParPerpHint(p) ?? p
    this.ctl.mouseMoved(q)
    const e = this.ctl.enforceControlParameters(q)
    if (!e) return false
    this.update(e)
    this.ctl.adaptParameters(e)
    this.onButtonPressed(e)
    return true
  }
  releaseButton(_p: XY) { this.finish(); return true }
  /** DrawSketchDefaultHandler::registerPressedKey (M: the next construction method, Esc) and the controllable
   *  handler's U, J, R, F (the widget's check boxes, or the tool's own) and Tab (the next parameter). */
  registerPressedKey(pressed: boolean, key: string): boolean {
    let used = false
    if (key === 'M' && pressed && !this.isLast) { this.iterateToNextConstructionMethod(); used = true }
    else if (key === 'Escape' && pressed) { this.cancelCurrentAction(); used = true }
    if (!pressed && !this.isLast) {
      if (key === 'U') { this.ctl.firstKeyShortcut(); used = true }
      if (key === 'J') { this.ctl.secondKeyShortcut(); used = true }
      if (key === 'R') { this.ctl.thirdKeyShortcut(); used = true }
      if (key === 'F') { this.ctl.fourthKeyShortcut(); used = true }
    }
    if (key === 'Tab' && !pressed) { this.ctl.tabShortcut(); used = true }
    return used || key === 'Escape' || key === 'Tab'
  }
  pressRightButton() { this.cancelCurrentAction() }
  cancelCurrentAction() { this.rightButtonOrEsc() }
  rightButtonOrEsc() { if (this.state === 0) this.quit(); else this.handleContinuousMode() }
  /** ConstructionMethodMachine::iterateToNextConstructionMethod. */
  protected iterateToNextConstructionMethod() { if (this.methods > 1) this.setConstructionMethod((this.method + 1) % this.methods) }
  /** setConstructionMethod, then DrawSketchControllableHandler::onConstructionMethodChanged: the hints, and the
   *  controller's (the cursor, a reset, the new method drawn at once where the cursor was). */
  setConstructionMethod(m: number) {
    this.method = m
    this.onMethodChanged()
    S.updateHints()
    this.ctl.onConstructionMethodChanged()
  }
  /** The tool's own reaction to a new construction method, before the controller's. */
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
  /** DrawSketchControllableHandler::onModeChanged: the cursor text and hints, the parameters of the new state, then
   *  DrawSketchDefaultHandler's (the angle snapping; at the end the shape is made: finish); if the tool goes on, the
   *  new state is drawn at once where the cursor was. */
  protected onModeChanged() {
    S.setEdit({ positionText: null })
    S.updateHints()
    this.ctl.onHandlerModeChanged()
    this.applyMode()
    if (!this.finish()) { this.afterModeChanged(); this.ctl.afterHandlerModeChanged() }
  }
  protected applyMode() { this.angleSnappingControl() }
  protected afterModeChanged() {}
  protected angleSnappingControl() { S.setAngleSnapping(false) }
  /** finish: at the end, the commands, the parameters' constraints (beforeCreateAutoConstraints), the
   *  auto-constraints, a solve, then continuous mode. */
  protected finish(): boolean {
    if (!this.isLast) return false
    S.setEdit({ positionText: null })
    try {
      this.executeCommands()
      if (this.autoConstraintSize > 0) {
        this.beforeCreateAutoConstraints()
        this.generateAutoConstraints(); this.createAutoConstraints()
      }
    } catch (e) { console.error(e); report('err', e instanceof Error ? e.message : String(e)) }
    S.solve()
    return this.handleContinuousMode()
  }
  /** DrawSketchControllableHandler::beforeCreateAutoConstraints: the controls' constraints first. */
  protected beforeCreateAutoConstraints() { this.addConstraints(this.ctl) }
  protected handleContinuousMode(): boolean {
    if (this.continuousMode) { this.reset(); return false }
    S.purgeHandler()
    return true
  }
  /** DrawSketchDefaultHandler::reset: the edit cleared, the tool's own reset (onReset, then the controls'), back to the
   *  first state. */
  reset() {
    S.setEdit({ curves: [], markers: [], positionText: null, extensionHint: null })
    this.resetParPerpHint()
    for (const s of this.sug) s.length = 0
    this.autos = []; this.shapeGeometry = []; this.shapeConstraints = []
    this.onReset()
    if (!this.resetsOwnControls) this.ctl.resetControls()
    this.nextMode = null
    if (this.state !== 0) this.setState(0)
    else this.applyMode()
    this.cursorTail = []
    S.applyCursor(); S.updateHints()
  }
  protected onReset() {}
  /** A tool whose onReset resets the controls itself, where FreeCAD's does (the polyline: before it sets the construction
   *  method back). */
  protected readonly resetsOwnControls: boolean = false

  // ── what the controller asks of the handler (OvpTool) ──
  currentState() { return this.state }
  get endState() { return this.states }
  isLastState() { return this.isLast }
  constructionMethod() { return this.method }
  get constructionMethodsCount() { return this.methods }
  setNextState(s: number | null) { this.nextMode = s }
  getNextState() { return this.nextMode }
  applyNextState() { if (this.nextMode !== null) { const n = this.nextMode; this.nextMode = null; this.setState(n) } }
  updateCursor() { S.applyCursor() }
  resetControls() { this.ctl.resetControls() }
  preselectAtPoint(p: XY) { S.preselectAtPoint(p) }
  updateDataAndDrawToPosition(p: XY) { this.update(p) }
  /** createWidget/isWidgetVisible: the Tool Parameters box shows for the tools that say so (most: unless the on-view
   *  parameters are off), with getToolWidgetText and getToolIcon as its header. */
  isWidgetVisible() { return false }
  toolWidgetText() { return '' }
  toolIcon() { return '' }
  ovpSpec(): OvpSpec { return { ovps: 0, widget: null, firstComboIsMethod: false } }
  ovpState(_i: number) { return 0 }
  configureOnViewParameters(_c: Controller) {}
  configureToolWidget(_c: Controller) {}
  doEnforceControlParameters(_c: Controller, p: XY): XY { return p }
  adaptParameters(_c: Controller, _p: XY) {}
  computeNextDrawSketchHandlerMode(_c: Controller) {}
  addConstraints(_c: Controller) {}
  addStepConstraints(_c: Controller) {}
  adaptDrawingToOnViewParameterChange(_c: Controller, _i: number, _v: number) {}
  adaptDrawingToParameterChange(_c: Controller, _i: number, _v: number) {}
  adaptDrawingToCheckboxChange(_c: Controller, _i: number, _v: boolean) {}
  /** True when the tool handled it; otherwise the first combo box sets the construction method. */
  adaptDrawingToComboboxChange(_c: Controller, _i: number, _v: number) { return false }
  doConstructionMethodChanged(_c: Controller) {}
  resetOnConstructionMethodChanged() { return this.resetOnMethodChange() }
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
  /** DrawSketchHandler::drawPositionAtCursor. A tool calls the controller's (this.ctl.drawPositionAtCursor), which
   *  leaves it out when the on-view parameters show the position (OnViewParameterVisibility 2). */
  drawPositionAtCursor(p: XY) { S.setEdit({ positionText: { at: p, text: S.positionString(p) } }) }
  /** drawDirectionAtCursor, drawWidthHeightAtCursor and drawDoubleAtCursor: only while the on-view parameters are
   *  off (the controller's check them; ShowCursorCoords). The length and angle as lengthToDisplayFormat writes them. */
  drawDirectionAtCursor(p: XY, origin: XY) {
    if (!sketcherParam<boolean>('Mod/Sketcher/General/ShowCursorCoords')) return
    const d = sub(p, origin), angle = getAngle(d, [1, 0])
    S.setEdit({ positionText: { at: p, text: ` (${S.lengthString(len(d))}, ${S.angleString((angle * 180) / Math.PI)})` } })
  }
  drawWidthHeightAtCursor(p: XY, a: number, b: number) {
    if (!sketcherParam<boolean>('Mod/Sketcher/General/ShowCursorCoords')) return
    S.setEdit({ positionText: { at: p, text: ` (${S.lengthString(a)} x ${S.lengthString(b)})` } })
  }
  drawDoubleAtCursor(p: XY, v: number, unit: 'Length' | 'Angle' = 'Length') {
    if (!sketcherParam<boolean>('Mod/Sketcher/General/ShowCursorCoords')) return
    S.setEdit({ positionText: { at: p, text: ` (${unit === 'Length' ? S.lengthString(v) : S.angleString((v * 180) / Math.PI)})` } })
  }
  protected clearCursorText() { S.setEdit({ positionText: null }) }
  hint(message: string, keys: string[]) { return { message, keys } }
}
const LMB = 'LMB', RMB = 'RMB', MOUSE_MOVE = 'MouseMove'

// ── Point (DrawSketchHandlerPoint.h) ─────────────────────────────────────────────────────────────────────────────
/** DSHPointController: a DrawSketchController with two on-view parameters, the point's X and Y (positioning). */
export class PointHandler extends DefaultHandler {
  readonly toolName = 'DSH_Point'
  protected readonly states = 1
  protected readonly autoConstraintSize = 1
  private editPoint: XY = [0, 0]
  crosshair() { return 'Sketcher_Pointer_Create_Point' }
  hints() { return [this.hint('%1 place a point', [LMB])] }
  protected update(p: XY) {
    if (this.state !== 0) return
    this.seekAndRender(this.sug[0], p, [0, 0])
    this.editPoint = this.lineExtensionSnapPoint() ?? p
    this.ctl.drawPositionAtCursor(this.editPoint)
  }
  protected executeCommands() {
    S.openCommand('Add sketch point')
    S.addGeometry(this.point([f6(this.editPoint[0]), f6(this.editPoint[1])]))
    S.commitCommand()
  }
  protected createAutoConstraints() {
    if (this.sug[0].length) { this.createAutoConstraintsDirect(this.sug[0], S.highestCurveIndex(), START); this.sug[0].length = 0 }
  }
  ovpSpec(): OvpSpec { return { ovps: 2, widget: null, firstComboIsMethod: false } }
  ovpState(_i: number) { return 0 }
  configureOnViewParameters(c: Controller) {
    c.onViewParameters[OVP.First].setLabelType('DISTANCEX')
    c.onViewParameters[OVP.Second].setLabelType('DISTANCEY')
  }
  adaptDrawingToOnViewParameterChange(c: Controller, i: number, v: number) {
    if (i === OVP.First) this.editPoint = [v, this.editPoint[1]]
    else if (i === OVP.Second) this.editPoint = [this.editPoint[0], v]
    c.onViewParameters[OVP.First].setPoints([0, 0], this.editPoint)
    c.onViewParameters[OVP.Second].setPoints([0, 0], this.editPoint)
  }
  doEnforceControlParameters(c: Controller, p: XY): XY {
    if (this.state !== 0) return p
    const [a, b] = c.onViewParameters
    return [a.isSet ? a.getValue() : p[0], b.isSet ? b.getValue() : p[1]]
  }
  adaptParameters(c: Controller, p: XY) {
    if (this.state !== 0) return
    const [a, b] = c.onViewParameters
    if (!a.isSet) c.setOnViewParameterValue(OVP.First, p[0])
    if (!b.isSet) c.setOnViewParameterValue(OVP.Second, p[1])
    const sameSign = p[0] * p[1] > 0
    a.setLabelAutoDistanceReverse(!sameSign); b.setLabelAutoDistanceReverse(sameSign)
    a.setPoints([0, 0], p); b.setPoints([0, 0], p)
  }
  computeNextDrawSketchHandlerMode(c: Controller) {
    if (this.state === 0 && c.onViewParameters[OVP.First].hasFinishedEditing && c.onViewParameters[OVP.Second].hasFinishedEditing) this.setNextState(this.states)
  }
  addConstraints(c: Controller) {
    const firstCurve = S.highestCurveIndex()
    const [a, b] = c.onViewParameters, x0 = a.getValue(), y0 = b.getValue()
    if (a.isSet && b.isSet && x0 === 0 && y0 === 0) constraintToAttachment([firstCurve, START], RT_PNT_ID, x0)
    else {
      if (a.isSet) constraintToAttachment([firstCurve, START], V_AXIS_ID, x0)
      if (b.isSet) constraintToAttachment([firstCurve, START], H_AXIS_ID, y0)
    }
  }
}

// ── Line (DrawSketchHandlerLine.h) ───────────────────────────────────────────────────────────────────────────────
/** LineConstructionMethod: OnePointLengthAngle (the default), OnePointWidthHeight, TwoPoints. DSHLineController: four
 *  on-view parameters (the start's X and Y; then length and angle, width and height, or the end's X and Y) and the
 *  widget's construction method combo box. */
export class LineHandler extends DefaultHandler {
  readonly toolName = 'DSH_Line'
  protected readonly states = 2
  protected readonly methods = 3
  protected readonly autoConstraintSize = 2
  private startPoint: XY = [0, 0]
  private endPoint: XY = [0, 0]
  private length = 0
  /** The direction signs taken when an on-view parameter is first set, so the mouse does not flip them. */
  private lengthSign = 0
  private widthSign = 0
  private capturedDirection: XY = [0, 0]
  constructor(method = 0) { super(); this.method = method }
  crosshair() { return this.method === 0 ? 'Sketcher_Pointer_Create_Line_Polar' : 'Sketcher_Pointer_Create_Line' }
  hints() { return [this.hint(this.state === 0 ? '%1 pick first point' : '%1 pick second point', [LMB]), this.hint('%1 switch mode', ['M'])] }
  getStartPointOfCurrentSegment() { return this.state === 1 ? this.startPoint : null }
  protected update(p: XY) {
    if (this.state === 0) {
      this.seekAndRender(this.sug[0], p, [0, 0])
      this.startPoint = this.lineExtensionSnapPoint() ?? p
      this.ctl.drawPositionAtCursor(this.startPoint)
    } else if (this.state === 1) {
      this.seekAndRender(this.sug[1], p, sub(p, this.startPoint))
      this.endPoint = this.lineExtensionSnapPoint() ?? p
      this.ctl.drawDirectionAtCursor(this.endPoint, this.startPoint)
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
  protected onReset() { this.lengthSign = 0; this.widthSign = 0; this.capturedDirection = [0, 0] }
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
  // the controller's specialisations
  isWidgetVisible() { return ovpVisibilityPref() !== 0 }
  toolWidgetText() { return 'Line Parameters' }
  toolIcon() { return 'Sketcher_CreateLine' }
  ovpSpec(): OvpSpec { return { ovps: 4, widget: { parameters: 0, checkboxes: 0, comboboxes: 1, lineEdits: 0 }, firstComboIsMethod: true } }
  ovpState(i: number) { return i < 2 ? 0 : 1 }
  configureToolWidget(c: Controller) {
    if (!c.init) {
      c.setComboboxElements(0, ['Point, length, angle', 'Point, width, height', '2 points'])
      const k = this.isConstructionMode() ? '_Constr' : ''
      c.setComboboxItemIcon(0, 0, `Sketcher_CreateLineAngleLength${k}`); c.setComboboxItemIcon(0, 1, `Sketcher_CreateLineLengthWidth${k}`); c.setComboboxItemIcon(0, 2, `Sketcher_CreateLine${k}`)
    }
    const o = c.onViewParameters
    o[OVP.First].setLabelType('DISTANCEX'); o[OVP.Second].setLabelType('DISTANCEY')
    if (this.method === 0) { o[OVP.Third].setLabelType('DISTANCE', 'Dimensioning'); o[OVP.Fourth].setLabelType('ANGLE', 'Dimensioning') }
    else if (this.method === 2) { o[OVP.Third].setLabelType('DISTANCEX', 'Positioning'); o[OVP.Fourth].setLabelType('DISTANCEY', 'Positioning') }
    else { o[OVP.Third].setLabelType('DISTANCEX', 'Dimensioning'); o[OVP.Fourth].setLabelType('DISTANCEY', 'Dimensioning') }
  }
  doEnforceControlParameters(c: Controller, p: XY): XY {
    const o = c.onViewParameters
    let [x, y] = p
    if (this.state === 0) {
      if (o[OVP.First].isSet) x = o[OVP.First].getValue()
      if (o[OVP.Second].isSet) y = o[OVP.Second].getValue()
      return [x, y]
    }
    if (this.state !== 1) return p
    const third = o[OVP.Third], fourth = o[OVP.Fourth]
    if (this.method === 1) {
      if (third.isSet) {
        const length = third.getValue()
        if (Math.abs(length) < CONFUSION && fourth.isSet && Math.abs(fourth.getValue()) < CONFUSION && fourth.hasFinishedEditing) {
          c.unsetOnViewParameter(third); this.lengthSign = 0; return [x, y]
        }
        if (this.lengthSign === 0) this.lengthSign = x - this.startPoint[0] >= 0 ? 1 : -1
        x = this.startPoint[0] + this.lengthSign * length
      }
      if (fourth.isSet) {
        const width = fourth.getValue()
        if (Math.abs(width) < CONFUSION && third.isSet && Math.abs(third.getValue()) < CONFUSION && third.hasFinishedEditing) {
          c.unsetOnViewParameter(fourth); this.widthSign = 0; return [x, y]
        }
        if (this.widthSign === 0) this.widthSign = y - this.startPoint[1] >= 0 ? 1 : -1
        y = this.startPoint[1] + this.widthSign * width
      }
    } else if (this.method === 0) {
      let dir = sub([x, y], this.startPoint)
      if (len(dir) < CONFUSION) dir = [1, dir[1]] // a null direction defaults to (1, 0)
      if (fourth.isSet) { const a = (fourth.getValue() * Math.PI) / 180; this.capturedDirection = [Math.cos(a), Math.sin(a)] }
      else this.capturedDirection = normalize(dir)
      if (third.isSet) {
        const length = third.getValue()
        if (length < CONFUSION && third.hasFinishedEditing) { c.unsetOnViewParameter(third); this.capturedDirection = [0, 0]; return [x, y] }
        ;[x, y] = add(this.startPoint, mul(this.capturedDirection, length))
      } else if (fourth.isSet) [x, y] = add(this.startPoint, project(sub([x, y], this.startPoint), this.capturedDirection)) // the angle only
    } else {
      if (third.isSet) x = third.getValue()
      if (fourth.isSet) y = fourth.getValue()
    }
    if (third.hasFinishedEditing && fourth.hasFinishedEditing && len(sub([x, y], this.startPoint)) < CONFUSION) {
      c.unsetOnViewParameter(third); c.unsetOnViewParameter(fourth); this.lengthSign = 0; this.widthSign = 0
    }
    return [x, y]
  }
  adaptParameters(c: Controller, p: XY) {
    const o = c.onViewParameters
    if (this.state === 0) {
      if (!o[OVP.First].isSet) c.setOnViewParameterValue(OVP.First, p[0])
      if (!o[OVP.Second].isSet) c.setOnViewParameterValue(OVP.Second, p[1])
      const sameSign = p[0] * p[1] > 0
      o[OVP.First].setLabelAutoDistanceReverse(!sameSign); o[OVP.Second].setLabelAutoDistanceReverse(sameSign)
      o[OVP.First].setPoints([0, 0], p); o[OVP.Second].setPoints([0, 0], p)
      return
    }
    if (this.state !== 1) return
    const third = o[OVP.Third], fourth = o[OVP.Fourth], vec = sub(this.endPoint, this.startPoint)
    if (this.method === 1) {
      if (!third.isSet) c.setOnViewParameterValue(OVP.Third, Math.abs(vec[0]))
      if (!fourth.isSet) c.setOnViewParameterValue(OVP.Fourth, Math.abs(vec[1]))
      const sameSign = vec[0] * vec[1] > 0
      third.setLabelAutoDistanceReverse(!sameSign); fourth.setLabelAutoDistanceReverse(sameSign)
      third.setPoints(this.startPoint, this.endPoint); fourth.setPoints(this.startPoint, this.endPoint)
    } else if (this.method === 0) {
      if (!third.isSet) c.setOnViewParameterValue(OVP.Third, len(vec))
      const range = angleOf(vec)
      if (!fourth.isSet) c.setOnViewParameterValue(OVP.Fourth, (range * 180) / Math.PI, 'Angle')
      else if (fourth.hasFinishedEditing && len(vec) > CONFUSION) {
        const ovpRange = (fourth.getValue() * Math.PI) / 180
        if (Math.abs(range - ovpRange) > CONFUSION) c.setOnViewParameterValue(OVP.Fourth, (range * 180) / Math.PI, 'Angle')
      }
      third.setPoints(this.startPoint, this.endPoint)
      fourth.setPoints(this.startPoint, [0, 0])
      fourth.setLabelRange(range)
    } else {
      if (!third.isSet) c.setOnViewParameterValue(OVP.Third, p[0])
      if (!fourth.isSet) c.setOnViewParameterValue(OVP.Fourth, p[1])
      const sameSign = p[0] * p[1] > 0
      third.setLabelAutoDistanceReverse(!sameSign); fourth.setLabelAutoDistanceReverse(sameSign)
      third.setPoints([0, 0], p); fourth.setPoints([0, 0], p)
    }
  }
  computeNextDrawSketchHandlerMode(c: Controller) {
    const o = c.onViewParameters
    if (this.state === 0 && o[OVP.First].hasFinishedEditing && o[OVP.Second].hasFinishedEditing) this.setNextState(1)
    else if (this.state === 1 && o[OVP.Third].hasFinishedEditing && o[OVP.Fourth].hasFinishedEditing) this.setNextState(this.states)
  }
  /** DSHLineController::addConstraints, with no auto-constraints diagnosed yet (they come after): each parameter set. */
  addConstraints(c: Controller) {
    const firstCurve = S.highestCurveIndex(), o = c.onViewParameters
    const x0 = o[OVP.First].getValue(), y0 = o[OVP.Second].getValue(), p3 = o[OVP.Third].getValue(), p4 = o[OVP.Fourth].getValue()
    const x0set = o[OVP.First].isSet, y0set = o[OVP.Second].isSet, p3set = o[OVP.Third].isSet, p4set = o[OVP.Fourth].isSet
    if (x0set && y0set && x0 === 0 && y0 === 0) constraintToAttachment([firstCurve, START], RT_PNT_ID, x0)
    else {
      if (x0set) constraintToAttachment([firstCurve, START], V_AXIS_ID, x0)
      if (y0set) constraintToAttachment([firstCurve, START], H_AXIS_ID, y0)
    }
    if (this.method === 1) {
      if (p3set) {
        if (Math.abs(p3) < CONFUSION) S.addConstraint(constraint('Vertical', firstCurve))
        else { const rev = this.endPoint[0] - this.startPoint[0] < 0; S.addConstraint(constraint('DistanceX', firstCurve, rev ? END : START, firstCurve, rev ? START : END, GEO_UNDEF, NONE, f6(Math.abs(p3)))) }
      }
      if (p4set) {
        if (Math.abs(p4) < CONFUSION) S.addConstraint(constraint('Horizontal', firstCurve))
        else { const rev = this.endPoint[1] - this.startPoint[1] < 0; S.addConstraint(constraint('DistanceY', firstCurve, rev ? END : START, firstCurve, rev ? START : END, GEO_UNDEF, NONE, f6(Math.abs(p4)))) }
      }
    } else if (this.method === 0) {
      if (p3set) S.addConstraint(constraint('Distance', firstCurve, NONE, GEO_UNDEF, NONE, GEO_UNDEF, NONE, f6(Math.abs(p3))))
      if (p4set) constraintLineByAngle(firstCurve, (p4 * Math.PI) / 180)
    } else {
      if (p3set) constraintToAttachment([firstCurve, END], V_AXIS_ID, p3)
      if (p4set) constraintToAttachment([firstCurve, END], H_AXIS_ID, p4)
    }
  }
}
// ── Polyline (DrawSketchHandlerPolyLine in DrawSketchHandlerLineSet.h) ──────────────────────────────────────────
/** PolyLineConstructionMethod: Line, Arc (M switches; the first segment is always a line). Each click adds a segment
 *  at once; R takes back the last point, F (or the box) toggles a fillet at each corner; Esc or the right button ends
 *  the polyline, a second Esc the tool. DSHPolyLineController: the first point's X and Y; then each segment's length and
 *  angle (to the previous segment), or an arc's radius, sweep and angle to the previous segment; their constraints go
 *  in as each segment is made (addStepConstraints). */
const polylineDoc = (): OPS.Doc => ({ geometry: S.getGeometry().map((g) => ({ ...g })), constraints: S.getConstraints().map((c) => ({ ...c })) })
const polylineMover: OPS.Mover = (d, geo, pos, to) => {
  const r = S.solveRaw({ geometry: d.geometry, constraints: d.constraints.map(SK.toCons), solve: false, drags: [{ geo, pos, to, update_geometry: true }] })
  return r && r.status_code === 0 && r.stored_geometry ? r.stored_geometry : null
}
export class PolylineHandler extends DefaultHandler {
  readonly toolName = 'DSH_PolyLine'
  protected readonly states = 2
  protected readonly methods = 2
  protected readonly autoConstraintSize = 2
  protected readonly resetsOwnControls = true
  private prevCursorPos: XY = [0, 0]
  private center: XY = [0, 0]
  private points: XY[] = []
  private geoEltIds: [number, PointPos][] = []
  private resetSeekSecond = false
  private resetEdge = true
  private fillet = false
  private previousDirectionAngle = 0
  private dirChangeAngle = 0
  private startAngle = 0
  private range = 0
  private angleToPrevious = 0
  private pos: PointPos = END
  private capturedDirection: XY = [0, 0]
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
    if (this.state === 0) { this.ctl.drawPositionAtCursor(p); this.seekAndRender(this.sug[0], p, [0, 0]) }
    else if (this.state === 1) {
      this.ctl.drawDirectionAtCursor(p, this.last())
      const a1 = angleOf(sub(p, this.last())) - this.previousDirectionAngle, a2 = a1 + (a1 < 0 ? 2 : -2) * Math.PI
      this.dirChangeAngle = Math.abs(a1 - this.dirChangeAngle) < Math.abs(a2 - this.dirChangeAngle) ? a1 : a2
      this.drawShape()
      this.seekAndRender(this.sug[1], p, this.method === 0 ? sub(p, this.last()) : [0, 0])
    }
  }
  /** getPreviousDirection: the direction at the end of the last segment (along an arc, its tangent). */
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
  private isPreviousArc() { return !!this.geoEltIds.length && SK.isArc(S.getGeometry()[this.geoEltIds[this.geoEltIds.length - 1][0]]) }
  /** getArcCenter: the arc from the last point, tangent to the current initial direction, through p; its signed radius. */
  private arcCenter(p: XY): { radius: number; center: XY } {
    const lp = this.last(), t = this.currentInitialDirection()
    const theta = getAngle(t, sub(p, lp))
    let radius = len(sub(p, lp)) / (2 * Math.sin(theta))
    const [x1, y1] = lp, x2 = x1 + t[0], y2 = y1 + t[1], [x3, y3] = p
    if ((x2 * y3 - x3 * y2) - (x1 * y3 - x3 * y1) + (x1 * y2 - x2 * y1) > 0) radius *= -1
    if (!Number.isFinite(radius)) radius = 0
    return { radius, center: add(lp, [radius * t[1], -radius * t[0]]) }
  }
  /** getFilletData: where the fillet at the last corner is picked on both segments, and its radius. */
  private filletData(newGeo: Geo, prevGeo: Geo, newGeoPos: PointPos, prevGeoPos: PointPos): { ref1: XY; ref2: XY; radius: number } {
    const lastPoint = this.last(), lastButOne = this.points[this.points.length - 2]
    let radius = Math.min(len(sub(this.prevCursorPos, lastPoint)) * 0.3, len(sub(lastButOne, lastPoint)) * 0.3)
    let ref1 = add(lastPoint, mul(normalize(sub(this.prevCursorPos, lastPoint)), radius))
    let ref2 = add(lastPoint, mul(normalize(sub(lastButOne, lastPoint)), radius))
    if (newGeo.type === 'LineSegment' && prevGeo.type === 'LineSegment') radius = OPS.suggestFilletRadius(newGeo, prevGeo, ref1, ref2)
    const devAngle = 0.3 // about 15°
    const onArc = (arc: Extract<Geo, { type: 'ArcOfCircle' }>, pos: PointPos): XY => {
      let s = arc.start_angle % (2 * Math.PI); if (s < 0) s += 2 * Math.PI
      const e = s + (arc.end_angle - arc.start_angle), span = e - s
      const a = pos === END ? e - Math.min(span, devAngle) : s + Math.min(span, devAngle)
      return [arc.center[0] + arc.radius * Math.cos(a), arc.center[1] + arc.radius * Math.sin(a)]
    }
    if (newGeo.type === 'ArcOfCircle') {
      ref1 = onArc(newGeo, newGeoPos)
      if (prevGeo.type === 'LineSegment') ref2 = add(lastPoint, mul(normalize(sub(ref2, lastPoint)), len(sub(lastPoint, ref1))))
    }
    if (prevGeo.type === 'ArcOfCircle') {
      ref2 = onArc(prevGeo, prevGeoPos)
      if (newGeo.type === 'LineSegment') ref1 = add(lastPoint, mul(normalize(sub(ref1, lastPoint)), len(sub(lastPoint, ref2))))
    }
    return { ref1, ref2, radius }
  }
  protected createShape(onlyOutline: boolean) {
    this.shapeGeometry = []; this.shapeConstraints = []
    if (!this.points.length) return
    const lp = this.last(), cd = sub(this.prevCursorPos, lp)
    if (len(cd) < CONFUSION) { this.resetEdge = true; return }
    this.pos = END
    let posId: PointPos = START
    const prevDir = this.previousDirection()
    let newGeo: Geo
    if (this.method === 0) newGeo = this.line(lp, this.prevCursorPos)
    else {
      if (this.resetEdge) {
        this.resetEdge = false
        const sign = prevDir[0] * (this.prevCursorPos[1] - lp[1]) - prevDir[1] * (this.prevCursorPos[0] - lp[0]) > 0 ? 1 : -1
        this.angleToPrevious = sign * (getAngle(cd, prevDir) - Math.PI)
        this.angleToPrevious = Math.round(this.angleToPrevious / (Math.PI / 2)) * (Math.PI / 2)
      }
      const { radius, center } = this.arcCenter(this.prevCursorPos)
      this.center = center
      if (radius === 0) return
      const rx = lp[0] - center[0], ry = lp[1] - center[1]
      this.startAngle = Math.atan2(ry, rx)
      const rxe = this.prevCursorPos[0] - center[0], rye = this.prevCursorPos[1] - center[1]
      let range = Math.atan2(-rxe * ry + rye * rx, rxe * rx + rye * ry)
      if (!Number.isFinite(range)) range = 0
      if (radius >= 0 && range > 0) range -= 2 * Math.PI
      if (radius < 0 && range < 0) range += 2 * Math.PI
      let s = this.startAngle, e = this.startAngle + range
      if (radius < 0) { [s, e] = [e, s]; posId = END; this.pos = START }
      newGeo = this.arc(center, s, e, Math.abs(radius))
      this.range = radius < 0 ? -2 * Math.PI + range : 2 * Math.PI + range
    }
    this.shapeGeometry.push(newGeo)
    if (onlyOutline && this.geoEltIds.length && this.fillet) {
      // the fillet as it would be made, drawn with the segment cut back to it
      const prevGeo = S.getGeometry()[this.geoEltIds[this.geoEltIds.length - 1][0]]
      const { ref1, ref2, radius } = this.filletData(newGeo, prevGeo, posId, this.geoEltIds[this.geoEltIds.length - 1][1])
      if (newGeo.type === 'LineSegment' && prevGeo?.type === 'LineSegment') {
        const f = OPS.createFilletGeometry(newGeo, prevGeo, ref1, ref2, radius)
        if (f) {
          const s = SK.getPoint([f.arc], 0, START)!, e = SK.getPoint([f.arc], 0, END)!
          this.shapeGeometry[0] = { ...newGeo, start: f.reverse ? s : e }
          this.shapeGeometry.push(this.isConstructionMode() ? { ...f.arc, construction: true } : f.arc)
        }
      }
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
  /** canGoToNextMode: the first click takes the first point; each next one makes its segment at once (with the
   *  parameters' constraints, the auto-constraints and a fillet at the corner); the polyline stays in this state until
   *  it closes. */
  protected canGoToNextMode() {
    if (this.state === 0) { this.points.push(this.prevCursorPos); return true }
    if (this.state !== 1) return true
    this.createShape(false)
    if (!this.shapeGeometry.length) return false
    this.resetParPerpHint()
    this.addShape()
    const geoId = S.highestCurveIndex()
    this.geoEltIds.push([geoId, this.pos])
    this.addStepConstraints(this.ctl)
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
    this.sug[0].length = 0; this.sug[1].length = 0; this.autos = []
    S.solve()
    if (this.fillet && this.geoEltIds.length > 1) {
      const n = this.geoEltIds.length, geoId1 = this.geoEltIds[n - 1][0], geoId2 = this.geoEltIds[n - 2][0]
      const geo = S.getGeometry(), newGeo = geo[geoId1], prevGeo = geo[geoId2]
      const newGeoPos = this.geoEltIds[n - 1][1] === START ? END : START, prevGeoPos = this.geoEltIds[n - 2][1]
      const { ref1, ref2, radius } = this.filletData(newGeo, prevGeo, newGeoPos, prevGeoPos)
      const d = polylineDoc()
      try {
        if (OPS.fillet(d, geoId1, geoId2, ref1, ref2, radius, true, true, false, polylineMover)) { S.setGeometry(d.geometry); S.setConstraints(d.constraints) }
      } catch (e) { report('err', e instanceof Error ? e.message : String(e)) }
      S.solve()
      if (this.isConstructionMode() && S.getGeometry()[geoId + 1]) S.toggleConstruction(geoId + 1)
    }
    const [lg, lpos] = this.geoEltIds[this.geoEltIds.length - 1]
    this.points.push(S.getPoint(lg, lpos)!)
    this.previousDirectionAngle = angleOf(this.previousDirection())
    if (!closed) {
      S.setAngleSnapping(true, this.last())
      this.resetSeekSecond = true
      this.resetEdge = true
      this.mouseMove(this.prevCursorPos)
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
  /** undoLastPoint: the last segment goes (and a fillet made with it, the previous segment put back to the corner). */
  private undoLastPoint() {
    if (this.state !== 1) return
    if (!this.geoEltIds.length) { this.quit(); return }
    const [delGeoId] = this.geoEltIds[this.geoEltIds.length - 1], lastGeoId = S.highestCurveIndex()
    const filletWasCreated = delGeoId < lastGeoId, pointWasCreated = delGeoId + 2 === lastGeoId
    this.geoEltIds.pop(); this.points.pop()
    if (filletWasCreated) {
      S.delGeometries([delGeoId, delGeoId + 1])
      if (this.geoEltIds.length) {
        S.solve()
        const [prevGeoId, prevPos] = this.geoEltIds[this.geoEltIds.length - 1]
        const moved = polylineMover(polylineDoc(), prevGeoId, prevPos, [f6(this.last()[0]), f6(this.last()[1])])
        if (moved) S.setGeometry(moved)
        if (pointWasCreated) {
          const pointGeoId = S.highestCurveIndex(), cs = S.getConstraints()
          for (let i = cs.length - 1; i >= 0; i--) {
            const c = cs[i]
            if (c.type !== 'PointOnObject') continue
            if ((c.first === pointGeoId && c.second === prevGeoId) || (c.first === prevGeoId && c.second === pointGeoId)) { S.delConstraints([i]); break }
          }
          const d = polylineDoc()
          OPS.transferConstraints(d, pointGeoId, START, prevGeoId, prevPos)
          S.setConstraints(d.constraints)
          S.delGeometries([delGeoId])
        }
      }
    } else S.delGeometries([delGeoId])
    S.solve()
    this.previousDirectionAngle = angleOf(this.previousDirection())
    S.setAngleSnapping(true, this.last())
    this.mouseMove(this.prevCursorPos)
  }
  protected onReset() {
    S.abortCommand()
    S.openCommand('Add sketch polyline')
    this.geoEltIds = []; this.points = []
    this.previousDirectionAngle = 0; this.dirChangeAngle = 0; this.angleToPrevious = 0; this.pos = END; this.capturedDirection = [0, 0]
    this.ctl.resetControls()
    this.setConstructionMethod(0)
    ensureViewFocus()
  }
  deactivated() { super.deactivated(); S.abortCommand() }
  // the controller's specialisations
  isWidgetVisible() { return true }
  toolWidgetText() { return 'Polyline Parameters' }
  toolIcon() { return 'Sketcher_CreatePolyline' }
  ovpSpec(): OvpSpec { return { ovps: this.method === 0 ? 4 : 5, widget: { parameters: 0, checkboxes: 1, comboboxes: 1, lineEdits: 0 }, firstComboIsMethod: true } }
  ovpState(i: number) { return i < 2 ? 0 : 1 }
  thirdKeyShortcut() { this.undoLastPoint(); return true }
  fourthKeyShortcut(c: Controller) { c.setCheckboxChecked(0, !c.getCheckboxChecked(0)); return true }
  configureToolWidget(c: Controller) {
    const k = this.isConstructionMode() ? '_Constr' : ''
    if (!c.init) {
      c.setComboboxElements(0, ['Line', 'Arc'])
      c.setCheckboxLabel(0, 'Fillet (F)')
      c.setCheckboxToolTip(0, 'Adds a fillet between the current and previous line')
      c.syncCheckboxToHandler(0, this.fillet)
      c.setComboboxItemIcon(0, 0, `Sketcher_CreateLine${k}`); c.setComboboxItemIcon(0, 1, `Sketcher_CreateArc${k}`)
      c.setCheckboxIcon(0, `Sketcher_CreateFillet${k}`)
    }
    const o = c.onViewParameters
    o[OVP.First].setLabelType('DISTANCEX'); o[OVP.Second].setLabelType('DISTANCEY')
    o[OVP.Third].setLabelType(this.method === 0 ? 'DISTANCE' : 'RADIUS', 'Dimensioning')
    o[OVP.Fourth].setLabelType('ANGLE', 'Dimensioning')
    if (this.method === 1) o[OVP.Fifth].setLabelType('ANGLE', 'Dimensioning')
    c.setCheckboxChecked(0, this.fillet)
  }
  adaptDrawingToCheckboxChange(_c: Controller, i: number, v: boolean) { if (i === 0) this.fillet = v; this.updateCursor() }
  doEnforceControlParameters(c: Controller, p: XY): XY {
    const o = c.onViewParameters
    let [x, y] = p
    if (this.state === 0) {
      if (o[OVP.First].isSet) x = o[OVP.First].getValue()
      if (o[OVP.Second].isSet) y = o[OVP.Second].getValue()
      return [x, y]
    }
    if (this.state !== 1) return p
    const third = o[OVP.Third], fourth = o[OVP.Fourth]
    if (this.resetSeekSecond) {
      // a new segment: its parameters start again, the focus on the first
      this.resetSeekSecond = false
      c.unsetOnViewParameter(third); c.unsetOnViewParameter(fourth)
      if (this.method === 1) c.unsetOnViewParameter(o[OVP.Fifth])
      c.keyManager.mode = 'ViewProvider'
      c.setFocusToOnViewParameter(OVP.Third)
      return [x, y]
    }
    const prevPoint = this.last()
    if (this.method === 0) {
      let dir = sub([x, y], prevPoint)
      if (fourth.isSet) { const a = this.previousDirectionAngle + (fourth.getValue() * Math.PI) / 180; this.capturedDirection = [Math.cos(a), Math.sin(a)] }
      else this.capturedDirection = normalize(dir)
      if (third.isSet) {
        if (len(dir) < CONFUSION) dir = [1, dir[1]]
        const length = third.getValue()
        if (length < CONFUSION && third.hasFinishedEditing) { c.unsetOnViewParameter(third); this.capturedDirection = [0, 0]; return [x, y] }
        ;[x, y] = add(prevPoint, mul(this.capturedDirection, length))
      } else if (fourth.isSet) [x, y] = add(prevPoint, project(sub([x, y], prevPoint), this.capturedDirection))
      if (third.hasFinishedEditing && fourth.hasFinishedEditing && len(sub([x, y], prevPoint)) < CONFUSION) {
        c.unsetOnViewParameter(third); c.unsetOnViewParameter(fourth); this.capturedDirection = [0, 0]
      }
    } else {
      if (third.isSet) {
        const radius = third.getValue()
        if (radius < CONFUSION) { c.unsetOnViewParameter(third); return [x, y] }
        const d0 = this.previousDirection(), a = this.angleToPrevious
        const dir: XY = [d0[0] * Math.cos(a) - d0[1] * Math.sin(a), d0[0] * Math.sin(a) + d0[1] * Math.cos(a)]
        const sign = dir[0] * (y - prevPoint[1]) - dir[1] * (x - prevPoint[0]) > 0 ? 1 : -1
        const normal: XY = [sign * -dir[1], sign * dir[0]]
        const center = add(prevPoint, mul(normalize(normal), radius))
        ;[x, y] = add(center, mul(normalize(sub([x, y], center)), radius))
      }
      if (fourth.isSet) {
        const ac = this.arcCenter([x, y]), sign = ac.radius < 0 ? -1 : 1, radius = Math.abs(ac.radius)
        const a = this.startAngle + sign * (fourth.getValue() * Math.PI) / 180
        ;[x, y] = add(ac.center, [Math.cos(a) * radius, Math.sin(a) * radius])
      }
      if (o[OVP.Fifth].isSet) {
        const a = (o[OVP.Fifth].getValue() * Math.PI) / 180
        if (this.angleToPrevious !== a) this.angleToPrevious = a
      }
    }
    return [x, y]
  }
  adaptParameters(c: Controller, p: XY) {
    const o = c.onViewParameters
    if (this.state === 0) {
      if (!o[OVP.First].isSet) c.setOnViewParameterValue(OVP.First, p[0])
      if (!o[OVP.Second].isSet) c.setOnViewParameterValue(OVP.Second, p[1])
      const sameSign = p[0] * p[1] > 0
      o[OVP.First].setLabelAutoDistanceReverse(!sameSign); o[OVP.Second].setLabelAutoDistanceReverse(sameSign)
      o[OVP.First].setPoints([0, 0], p); o[OVP.Second].setPoints([0, 0], p)
      return
    }
    if (this.state !== 1) return
    const third = o[OVP.Third], fourth = o[OVP.Fourth], prevPoint: XY = this.points.length ? this.last() : [0, 0]
    if (this.method === 0) {
      const vec = sub(p, prevPoint)
      if (!third.isSet) c.setOnViewParameterValue(OVP.Third, len(vec))
      const range = (this.dirChangeAngle * 180) / Math.PI
      if (!fourth.isSet) c.setOnViewParameterValue(OVP.Fourth, range, 'Angle')
      else if (fourth.hasFinishedEditing && len(vec) > CONFUSION && Math.abs(range - fourth.getValue()) > CONFUSION) c.setOnViewParameterValue(OVP.Fourth, range, 'Angle')
      third.setPoints(prevPoint, p)
      fourth.setPoints(prevPoint, [0, 0])
      fourth.setLabelStartAngle(this.previousDirectionAngle)
      fourth.setLabelRange(this.dirChangeAngle)
    } else {
      const fifth = o[OVP.Fifth], vec = sub(p, this.center)
      if (!third.isSet) c.setOnViewParameterValue(OVP.Third, len(vec))
      if (!fourth.isSet) c.setOnViewParameterValue(OVP.Fourth, (this.range * 180) / Math.PI, 'Angle')
      if (!fifth.isSet) c.setOnViewParameterValue(OVP.Fifth, (this.angleToPrevious * 180) / Math.PI, 'Angle')
      third.setPoints(this.center, p)
      fourth.setPoints(this.center, [0, 0])
      fourth.setLabelStartAngle(this.startAngle)
      fourth.setLabelRange(this.range)
      fifth.setPoints(prevPoint, [0, 0])
      fifth.setLabelStartAngle(this.previousDirectionAngle)
      fifth.setLabelRange(this.angleToPrevious)
    }
  }
  computeNextDrawSketchHandlerMode(c: Controller) {
    const o = c.onViewParameters
    if (this.state === 0) {
      if (o[OVP.First].hasFinishedEditing && o[OVP.Second].hasFinishedEditing) this.onButtonPressed([o[OVP.First].getValue(), o[OVP.Second].getValue()])
    } else if (this.state === 1 && o[OVP.Third].hasFinishedEditing && o[OVP.Fourth].hasFinishedEditing) {
      this.canGoToNextMode() // the segment, without leaving this state
      c.unsetOnViewParameter(o[OVP.Third]); c.unsetOnViewParameter(o[OVP.Fourth])
      if (this.method === 1) c.unsetOnViewParameter(o[OVP.Fifth])
    }
  }
  doConstructionMethodChanged(c: Controller) {
    if (this.method === 1) {
      if (!this.geoEltIds.length) { this.setConstructionMethod(0); return } // the first segment is a line
      this.resetEdge = true
    }
    c.resetOnViewParameters()
    this.configureToolWidget(c)
    c.setModeOnViewParameters()
    c.syncConstructionMethodComboboxToHandler()
  }
  resetOnConstructionMethodChanged() { return false }
  /** addStepConstraints: the first point's position with the first segment, then each segment's length and angle (to
   *  the previous line, or the H axis), or radius and sweep. */
  addStepConstraints(c: Controller) {
    const lastCurve = S.highestCurveIndex(), o = c.onViewParameters
    if (this.geoEltIds.length === 1) {
      const x0 = o[OVP.First].getValue(), y0 = o[OVP.Second].getValue(), x0set = o[OVP.First].isSet, y0set = o[OVP.Second].isSet
      if (x0set && y0set && x0 === 0 && y0 === 0) constraintToAttachment([lastCurve, START], RT_PNT_ID, x0)
      else {
        if (x0set) constraintToAttachment([lastCurve, START], V_AXIS_ID, x0)
        if (y0set) constraintToAttachment([lastCurve, START], H_AXIS_ID, y0)
      }
      c.deactivateOnViewParameter(OVP.First); c.deactivateOnViewParameter(OVP.Second)
    }
    const p3 = o[OVP.Third].getValue(), p4 = o[OVP.Fourth].getValue(), p3set = o[OVP.Third].isSet, p4set = o[OVP.Fourth].isSet
    if (this.method === 0) {
      if (p3set) S.addConstraint(constraint('Distance', lastCurve, NONE, GEO_UNDEF, NONE, GEO_UNDEF, NONE, f6(Math.abs(p3))))
      if (p4set) {
        if (this.geoEltIds.length > 1) { if (!this.isPreviousArc()) constraint2LinesByAngle(this.geoEltIds[this.geoEltIds.length - 2][0], lastCurve, (p4 * Math.PI) / 180) }
        else constraintLineByAngle(lastCurve, (p4 * Math.PI) / 180)
      }
    } else {
      if (p3set) S.addConstraint(constraint('Radius', lastCurve, NONE, GEO_UNDEF, NONE, GEO_UNDEF, NONE, f6(Math.abs(p3))))
      if (p4set) S.addConstraint(constraint('Angle', lastCurve, NONE, GEO_UNDEF, NONE, GEO_UNDEF, NONE, f6(Math.abs((p4 * Math.PI) / 180))))
    }
  }
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
      this.ctl.drawPositionAtCursor(p)
      if (this.method === 0) this.centerPoint = p; else this.firstPoint = p
      this.seekAndRender(this.sug[0], p, [0, 0])
    } else if (this.state === 1) {
      if (this.method === 0) { this.firstPoint = p; this.startAngle = angleOf(sub(this.firstPoint, this.centerPoint)) }
      else { this.centerPoint = add(mul(sub(p, this.firstPoint), 0.5), this.firstPoint); this.secondPoint = p }
      this.radius = len(sub(p, this.centerPoint))
      this.drawShape()
      if (this.method === 0) this.ctl.drawDirectionAtCursor(p, this.centerPoint); else this.ctl.drawPositionAtCursor(p)
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
      if (this.method === 0) { this.startAngle = backup; this.ctl.drawDoubleAtCursor(p, this.arcAngle, "Angle"); this.seekAndRender(this.sug[2], p, [0, 0]) }
      else { this.ctl.drawPositionAtCursor(p); this.seekAndRender(this.sug[2], p, [0, 0], 'curve') }
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
  // DSHArcController: the centre's X and Y, the radius and start angle, the arc's angle; or three rim points' X and Y
  isWidgetVisible() { return true }
  toolWidgetText() { return 'Arc Parameters' }
  toolIcon() { return 'Sketcher_CreateArc' }
  ovpSpec(): OvpSpec { return { ovps: this.method === 0 ? 5 : 6, widget: { parameters: 0, checkboxes: 0, comboboxes: 1, lineEdits: 0 }, firstComboIsMethod: true } }
  ovpState(i: number) { return Math.trunc(i / 2) }
  configureToolWidget(c: Controller) {
    if (!c.init) {
      c.setComboboxElements(0, ['Center', '3 rim points'])
      const k = this.isConstructionMode() ? '_Constr' : ''
      c.setComboboxItemIcon(0, 0, `Sketcher_CreateArc${k}`); c.setComboboxItemIcon(0, 1, `Sketcher_Create3PointArc${k}`)
    }
    const o = c.onViewParameters
    o[OVP.First].setLabelType('DISTANCEX'); o[OVP.Second].setLabelType('DISTANCEY')
    if (this.method === 1) {
      o[OVP.Third].setLabelType('DISTANCEX'); o[OVP.Fourth].setLabelType('DISTANCEY')
      o[OVP.Fifth].setLabelType('DISTANCEX'); o[OVP.Sixth].setLabelType('DISTANCEY')
    } else {
      o[OVP.Third].setLabelType('RADIUS', 'Dimensioning'); o[OVP.Fourth].setLabelType('ANGLE', 'Dimensioning'); o[OVP.Fifth].setLabelType('ANGLE', 'Dimensioning')
    }
  }
  doEnforceControlParameters(c: Controller, p: XY): XY {
    const o = c.onViewParameters
    let [x, y] = p
    if (this.state === 0) {
      if (o[OVP.First].isSet) x = o[OVP.First].getValue()
      if (o[OVP.Second].isSet) y = o[OVP.Second].getValue()
    } else if (this.state === 1) {
      const third = o[OVP.Third], fourth = o[OVP.Fourth]
      if (this.method === 0) {
        let dir = sub([x, y], this.centerPoint)
        if (len(dir) < CONFUSION) dir = [1, dir[1]]
        let radius = len(dir)
        if (third.isSet) {
          radius = third.getValue()
          if (radius < CONFUSION && third.hasFinishedEditing) { c.unsetOnViewParameter(third); return [x, y] }
          ;[x, y] = add(this.centerPoint, mul(normalize(dir), radius))
        }
        if (fourth.isSet) { const a = (fourth.getValue() * Math.PI) / 180; x = this.centerPoint[0] + Math.cos(a) * radius; y = this.centerPoint[1] + Math.sin(a) * radius }
      } else {
        if (third.isSet) x = third.getValue()
        if (fourth.isSet) y = fourth.getValue()
        if (third.hasFinishedEditing && fourth.hasFinishedEditing && len(sub([x, y], this.firstPoint)) < CONFUSION) { c.unsetOnViewParameter(third); c.unsetOnViewParameter(fourth) }
      }
    } else if (this.state === 2) {
      const fifth = o[OVP.Fifth]
      if (this.method === 0) {
        if (fifth.isSet) {
          const arcAngle = (fifth.getValue() * Math.PI) / 180
          if (Math.abs(arcAngle) % (2 * Math.PI) < CONFUSION && fifth.hasFinishedEditing) { c.unsetOnViewParameter(fifth); return [x, y] }
          this.arcAngle = arcAngle
          const a = this.startAngle + arcAngle
          x = this.centerPoint[0] + Math.cos(a) * this.radius; y = this.centerPoint[1] + Math.sin(a) * this.radius
        }
      } else {
        const sixth = o[OVP.Sixth]
        if (fifth.isSet) x = fifth.getValue()
        if (sixth.isSet) y = sixth.getValue()
      }
    }
    return [x, y]
  }
  adaptParameters(c: Controller, p: XY) {
    const o = c.onViewParameters
    const xy = (a: number, b: number) => {
      if (!o[a].isSet) c.setOnViewParameterValue(a, p[0])
      if (!o[b].isSet) c.setOnViewParameterValue(b, p[1])
      const sameSign = p[0] * p[1] > 0
      o[a].setLabelAutoDistanceReverse(!sameSign); o[b].setLabelAutoDistanceReverse(sameSign)
      o[a].setPoints([0, 0], p); o[b].setPoints([0, 0], p)
    }
    if (this.state === 0) xy(OVP.First, OVP.Second)
    else if (this.state === 1) {
      if (this.method === 0) {
        if (!o[OVP.Third].isSet) c.setOnViewParameterValue(OVP.Third, this.radius)
        if (!o[OVP.Fourth].isSet) c.setOnViewParameterValue(OVP.Fourth, (this.startAngle * 180) / Math.PI, 'Angle')
        o[OVP.Third].setPoints(this.centerPoint, p)
        o[OVP.Fourth].setPoints(this.centerPoint, [0, 0])
        o[OVP.Fourth].setLabelRange(this.startAngle)
      } else xy(OVP.Third, OVP.Fourth)
    } else if (this.state === 2) {
      if (this.method === 0) {
        if (!o[OVP.Fifth].isSet) c.setOnViewParameterValue(OVP.Fifth, (this.arcAngle * 180) / Math.PI, 'Angle')
        o[OVP.Fifth].setPoints(this.centerPoint, [0, 0])
        o[OVP.Fifth].setLabelStartAngle(this.startAngle)
        o[OVP.Fifth].setLabelRange(this.arcAngle)
      } else xy(OVP.Fifth, OVP.Sixth)
    }
  }
  computeNextDrawSketchHandlerMode(c: Controller) {
    const o = c.onViewParameters
    if (this.state === 0) { if (o[OVP.First].hasFinishedEditing && o[OVP.Second].hasFinishedEditing) this.setNextState(1) }
    else if (this.state === 1) { if (o[OVP.Third].hasFinishedEditing && o[OVP.Fourth].hasFinishedEditing) this.setNextState(2) }
    else if (this.state === 2) {
      if (this.method === 0) { if (o[OVP.Fifth].hasFinishedEditing) this.setNextState(this.states) }
      else if (o[OVP.Fifth].hasFinishedEditing && o[OVP.Sixth].hasFinishedEditing) this.setNextState(this.states)
    }
  }
  doConstructionMethodChanged() { S.updateHints() }
  addConstraints(c: Controller) {
    const firstCurve = S.highestCurveIndex(), o = c.onViewParameters
    const x0 = o[OVP.First].getValue(), y0 = o[OVP.Second].getValue(), p3 = o[OVP.Third].getValue(), p4 = o[OVP.Fourth].getValue()
    const x0set = o[OVP.First].isSet, y0set = o[OVP.Second].isSet, p3set = o[OVP.Third].isSet, p4set = o[OVP.Fourth].isSet, p5set = o[OVP.Fifth].isSet
    const pos1 = this.method === 0 ? MID : this.arcPos1
    if (x0set && y0set && x0 === 0 && y0 === 0) constraintToAttachment([firstCurve, pos1], RT_PNT_ID, 0)
    else {
      if (x0set) constraintToAttachment([firstCurve, pos1], V_AXIS_ID, x0)
      if (y0set) constraintToAttachment([firstCurve, pos1], H_AXIS_ID, y0)
    }
    if (this.method === 0) {
      if (p3set) S.addConstraint(constraint('Radius', firstCurve, NONE, GEO_UNDEF, NONE, GEO_UNDEF, NONE, f6(Math.abs(p3))))
      if (p5set) S.addConstraint(constraint('Angle', firstCurve, NONE, GEO_UNDEF, NONE, GEO_UNDEF, NONE, f6(Math.abs(this.arcAngle))))
    } else if (p3set && p4set && p3 === 0 && p4 === 0) constraintToAttachment([firstCurve, this.arcPos2], RT_PNT_ID, 0)
    else {
      if (p3set) constraintToAttachment([firstCurve, this.arcPos2], V_AXIS_ID, p3)
      if (p4set) constraintToAttachment([firstCurve, this.arcPos2], H_AXIS_ID, p4)
    }
  }
}

// ── Circle (DrawSketchHandlerCircle.h) ───────────────────────────────────────────────────────────────────────────
/** Mod/Sketcher/dimensioning's DimensioningDiameter and DimensioningRadius (both on): a circle's dimension is its
 *  diameter unless only the radius is asked for. */
const useRadius = () => sketcherParam<boolean>('Mod/Sketcher/dimensioning/DimensioningRadius', true) && !sketcherParam<boolean>('Mod/Sketcher/dimensioning/DimensioningDiameter', true)
/** CircleEllipseConstructionMethod: Center, ThreeRim. DSHCircleController: the centre's X and Y, then the diameter (or
 *  radius); or the three rim points' X and Y. */
export class CircleHandler extends DefaultHandler {
  readonly toolName = 'DSH_Circle'
  protected readonly states = 3
  protected readonly methods = 2
  protected readonly autoConstraintSize = 3
  private centerPoint: XY = [0, 0]; private firstPoint: XY = [0, 0]; private secondPoint: XY = [0, 0]; private radius = 0
  private isDiameter = true
  constructor(method = 0) { super(); this.method = method }
  crosshair() { return this.method === 0 ? 'Sketcher_Pointer_Create_Circle' : 'Sketcher_Pointer_Create_3PointCircle' }
  hints() {
    const c = ['%1 pick circle center', '%1 pick rim point'], r = ['%1 pick first rim point', '%1 pick second rim point', '%1 pick third rim point']
    return [this.hint((this.method === 0 ? c : r)[Math.min(this.state, this.method === 0 ? 1 : 2)], [LMB]), this.hint('%1 switch mode', ['M'])]
  }
  protected update(p: XY) {
    if (this.state === 0) {
      this.ctl.drawPositionAtCursor(p)
      if (this.method === 0) { this.centerPoint = p; this.seekAndRender(this.sug[0], p, [0, 0]) }
      else { this.firstPoint = p; this.seekAndRender(this.sug[0], p, [0, 0], 'curve') }
    } else if (this.state === 1) {
      if (this.method === 1) this.centerPoint = add(mul(sub(p, this.firstPoint), 0.5), this.firstPoint)
      this.secondPoint = p
      this.radius = len(sub(p, this.centerPoint))
      this.drawShape()
      if (this.method === 0) this.ctl.drawDoubleAtCursor(p, this.radius); else this.ctl.drawPositionAtCursor(p)
      this.seekAndRender(this.sug[1], p, this.method === 0 ? sub(p, this.centerPoint) : [0, 0], 'curve')
    } else if (this.state === 2) {
      if (areCollinear(this.firstPoint, this.secondPoint, p)) return
      this.centerPoint = circleCenter(this.firstPoint, this.secondPoint, p)
      this.radius = len(sub(p, this.centerPoint))
      this.ctl.drawPositionAtCursor(p)
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
  protected createAutoConstraints() { this.createGeneratedAutoConstraints(true); for (const s of this.sug.slice(0, 3)) s.length = 0 }
  isWidgetVisible() { return true }
  toolWidgetText() { return 'Circle Parameters' }
  toolIcon() { return 'Sketcher_CreateCircle' }
  ovpSpec(): OvpSpec { return { ovps: this.method === 0 ? 3 : 6, widget: { parameters: 0, checkboxes: 0, comboboxes: 1, lineEdits: 0 }, firstComboIsMethod: true } }
  ovpState(i: number) { return this.method === 0 ? (i < 2 ? 0 : 1) : Math.trunc(i / 2) }
  configureToolWidget(c: Controller) {
    if (!c.init) {
      c.setComboboxElements(0, ['Center', '3 rim points'])
      const k = this.isConstructionMode() ? '_Constr' : ''
      c.setComboboxItemIcon(0, 0, `Sketcher_CreateCircle${k}`); c.setComboboxItemIcon(0, 1, `Sketcher_Create3PointCircle${k}`)
      if (useRadius()) this.isDiameter = false
    }
    const o = c.onViewParameters
    o[OVP.First].setLabelType('DISTANCEX'); o[OVP.Second].setLabelType('DISTANCEY')
    if (this.method === 1) {
      o[OVP.Third].setLabelType('DISTANCEX'); o[OVP.Fourth].setLabelType('DISTANCEY')
      o[OVP.Fifth].setLabelType('DISTANCEX'); o[OVP.Sixth].setLabelType('DISTANCEY')
    } else o[OVP.Third].setLabelType(useRadius() ? 'RADIUS' : 'DIAMETER', 'Dimensioning')
  }
  doEnforceControlParameters(c: Controller, p: XY): XY {
    const o = c.onViewParameters
    let [x, y] = p
    if (this.state === 0) {
      if (o[OVP.First].isSet) x = o[OVP.First].getValue()
      if (o[OVP.Second].isSet) y = o[OVP.Second].getValue()
    } else if (this.state === 1) {
      const third = o[OVP.Third]
      if (this.method === 0) {
        if (third.isSet) {
          const radius = (this.isDiameter ? 0.5 : 1) * third.getValue()
          if (radius < CONFUSION && third.hasFinishedEditing) { c.unsetOnViewParameter(third); return [x, y] }
          let dir = sub([x, y], this.centerPoint)
          if (len(dir) < CONFUSION) dir = [1, dir[1]]
          ;[x, y] = add(this.centerPoint, mul(normalize(dir), radius))
        }
      } else {
        const fourth = o[OVP.Fourth]
        if (third.isSet) x = third.getValue()
        if (fourth.isSet) y = fourth.getValue()
        if (third.hasFinishedEditing && fourth.hasFinishedEditing && len(sub([x, y], this.firstPoint)) < CONFUSION) { c.unsetOnViewParameter(third); c.unsetOnViewParameter(fourth) }
      }
    } else if (this.state === 2) {
      const fifth = o[OVP.Fifth], sixth = o[OVP.Sixth]
      if (fifth.isSet) x = fifth.getValue()
      if (sixth.isSet) y = sixth.getValue()
      if (fifth.hasFinishedEditing && sixth.hasFinishedEditing && areCollinear(this.firstPoint, this.secondPoint, [x, y])) { c.unsetOnViewParameter(fifth); c.unsetOnViewParameter(sixth) }
    }
    return [x, y]
  }
  adaptParameters(c: Controller, p: XY) {
    const o = c.onViewParameters
    const xy = (a: number, b: number) => {
      if (!o[a].isSet) c.setOnViewParameterValue(a, p[0])
      if (!o[b].isSet) c.setOnViewParameterValue(b, p[1])
      const sameSign = p[0] * p[1] > 0
      o[a].setLabelAutoDistanceReverse(!sameSign); o[b].setLabelAutoDistanceReverse(sameSign)
      o[a].setPoints([0, 0], p); o[b].setPoints([0, 0], p)
    }
    if (this.state === 0) xy(OVP.First, OVP.Second)
    else if (this.state === 1) {
      if (this.method === 0) {
        const r = useRadius()
        if (!o[OVP.Third].isSet) c.setOnViewParameterValue(OVP.Third, this.radius * (r ? 1 : 2))
        const start = r ? this.centerPoint : sub(this.centerPoint, sub(p, this.centerPoint))
        o[OVP.Third].setPoints(start, p)
      } else xy(OVP.Third, OVP.Fourth)
    } else if (this.state === 2) xy(OVP.Fifth, OVP.Sixth)
  }
  computeNextDrawSketchHandlerMode(c: Controller) {
    const o = c.onViewParameters
    if (this.state === 0) { if (o[OVP.First].hasFinishedEditing && o[OVP.Second].hasFinishedEditing) this.setNextState(1) }
    else if (this.state === 1) {
      if (o[OVP.Third].hasFinishedEditing && this.method === 0) this.setNextState(this.states)
      else if (o.length > 3 && (o[OVP.Third].hasFinishedEditing || o[OVP.Fourth].hasFinishedEditing) && this.method === 1) this.setNextState(2)
    } else if (this.state === 2) { if (o[OVP.Fifth].hasFinishedEditing && o[OVP.Sixth].hasFinishedEditing) this.setNextState(this.states) }
  }
  doConstructionMethodChanged() { S.updateHints() }
  addConstraints(c: Controller) {
    if (this.method !== 0) return // no constraint for a circle by three rim points
    const firstCurve = S.highestCurveIndex(), o = c.onViewParameters
    if (o[OVP.First].isSet) constraintToAttachment([firstCurve, MID], V_AXIS_ID, o[OVP.First].getValue())
    if (o[OVP.Second].isSet) constraintToAttachment([firstCurve, MID], H_AXIS_ID, o[OVP.Second].getValue())
    if (o[OVP.Third].isSet) {
      S.addConstraint(this.isDiameter ? constraint('Diameter', firstCurve, NONE, GEO_UNDEF, NONE, GEO_UNDEF, NONE, f6(this.radius * 2))
        : constraint('Radius', firstCurve, NONE, GEO_UNDEF, NONE, GEO_UNDEF, NONE, f6(this.radius)))
      S.moveConstraint(S.getConstraints().length - 1, c.prevCursorPosition)
    }
  }
}
// ── Rectangle (DrawSketchHandlerRectangle.h) ─────────────────────────────────────────────────────────────────────
/** Base::sgn. */
const sgn = (v: number) => (v > 0 ? 1 : 0) - (v < 0 ? 1 : 0)
/** RectangleConstructionMethod: Diagonal (two corners), CenterAndCorner, ThreePoints (three corners: any
 *  parallelogram), CenterAnd3Points (the centre and two corners). With "Rounded corners (U)" a click more sets the
 *  corner radius, with "Frame (J)" one more the frame's thickness (a second rectangle at that offset). FiveSeekEnd.
 *  DSHRectangleController: the first corner's (or the centre's) X and Y; then the width and height (DISTANCEX and
 *  DISTANCEY), or for three points a side's length and angle and the other side's length and the angle between them,
 *  or for the centre and three points the corner's X and Y and the second side's length and angle; then the radius and
 *  the thickness. The widget: the construction method and the two check boxes. */
export class RectangleHandler extends DefaultHandler {
  readonly toolName = 'DSH_Rectangle'
  protected readonly states = 5
  protected readonly methods = 4
  protected readonly autoConstraintSize = 3
  private center: XY = [0, 0]; private corner1: XY = [0, 0]; private corner2: XY = [0, 0]; private corner3: XY = [0, 0]; private corner4: XY = [0, 0]
  private frameCorner1: XY = [0, 0]; private frameCorner2: XY = [0, 0]; private frameCorner3: XY = [0, 0]; private frameCorner4: XY = [0, 0]
  private corner2Initial: XY = [0, 0]
  private center1: XY = [0, 0]; private center2: XY = [0, 0]; private center3: XY = [0, 0]; private center4: XY = [0, 0]
  private cornersReversed = false
  private radius = 0; private length = 0; private width = 0; private thickness = 0; private radiusFrame = 0
  private angle = 0; private angle123 = 0; private angle412 = 0
  private firstCurve = GEO_UNDEF; private constructionPointOneId = GEO_UNDEF; private constructionPointTwoId = GEO_UNDEF
  private constructionPointThreeId = GEO_UNDEF; private centerPointId = GEO_UNDEF; private side = 0
  /** The direction signs taken when a width or height is first typed, so that the mouse does not flip them (#23459). */
  private lengthSign = 0; private widthSign = 0
  constructor(method = 0, private roundCorners = false, private makeFrame = false) { super(); this.method = method }
  private get twoCorner() { return this.method === 0 || this.method === 1 }
  crosshair() {
    const m = this.method
    if (!this.roundCorners && !this.makeFrame) return m === 1 ? 'Sketcher_Pointer_Create_Box_Center' : m === 2 ? 'Sketcher_Pointer_Create_Box_3Points' : m === 3 ? 'Sketcher_Pointer_Create_Box_3Points_Center' : 'Sketcher_Pointer_Create_Box'
    if (this.roundCorners && !this.makeFrame) return m === 1 ? 'Sketcher_Pointer_Oblong_Center' : 'Sketcher_Pointer_Oblong'
    if (!this.roundCorners) return m === 1 ? 'Sketcher_Pointer_Create_Frame_Center' : 'Sketcher_Pointer_Create_Frame'
    return m === 1 ? 'Sketcher_Pointer_Oblong_Frame_Center' : 'Sketcher_Pointer_Oblong_Frame'
  }
  hints() {
    const texts = [
      ['%1 pick first corner', '%1 pick opposite corner', '%1 set corner radius or frame thickness', '%1 set frame thickness'],
      ['%1 pick center', '%1 pick corner', '%1 set corner radius or frame thickness', '%1 set frame thickness'],
      ['%1 pick first corner', '%1 pick second corner', '%1 pick third corner', '%1 set corner radius or frame thickness'],
      ['%1 pick center', '%1 pick first corner', '%1 pick second corner', '%1 set corner radius or frame thickness']][this.method]
    if (this.state > 3) return []
    const first = this.hint(texts[this.state], [this.twoCorner ? (this.state < 2 ? LMB : MOUSE_MOVE) : this.state < 3 ? LMB : MOUSE_MOVE])
    return [first, this.hint('%1 switch mode', ['M']), this.hint('%1 toggle rounded corners', ['U']), this.hint('%1 toggle frame', ['J'])]
  }
  protected update(p: XY) {
    const pi = Math.PI
    if (this.state === 0) {
      this.ctl.drawPositionAtCursor(p)
      if (this.method === 0 || this.method === 2) this.corner1 = p
      else this.center = p
      this.seekAndRender(this.sug[0], p, [0, 0])
    } else if (this.state === 1) {
      if (this.method === 0) {
        this.ctl.drawDirectionAtCursor(p, this.corner1)
        // corners 2 and 4 swapped so that the corners run counter-clockwise
        this.corner3 = p
        if ((this.corner3[0] - this.corner1[0]) * (this.corner3[1] - this.corner1[1]) > 0) { this.corner2 = [p[0], this.corner1[1]]; this.corner4 = [this.corner1[0], p[1]]; this.cornersReversed = false }
        else { this.corner4 = [p[0], this.corner1[1]]; this.corner2 = [this.corner1[0], p[1]]; this.cornersReversed = true }
        this.angle123 = pi / 2; this.angle412 = pi / 2
      } else if (this.method === 1) {
        this.ctl.drawDirectionAtCursor(p, this.center)
        this.corner1 = sub(this.center, sub(p, this.center))
        this.corner3 = p
        if (sgn(this.corner3[0] - this.corner1[0]) * sgn(this.corner3[1] - this.corner1[1]) > 0) { this.corner2 = [p[0], this.corner1[1]]; this.corner4 = [this.corner1[0], p[1]]; this.cornersReversed = false }
        else { this.corner4 = [p[0], this.corner1[1]]; this.corner2 = [this.corner1[0], p[1]]; this.cornersReversed = true }
        this.angle123 = pi / 2; this.angle412 = pi / 2
      } else if (this.method === 2) {
        this.ctl.drawDirectionAtCursor(p, this.corner1)
        this.corner2 = p
        const d = sub(this.corner2, this.corner1), perpendicular: XY = [-d[1], d[0]]
        this.corner3 = add(this.corner2, perpendicular); this.corner4 = add(this.corner1, perpendicular)
        this.angle123 = pi / 2; this.angle412 = pi / 2
        this.corner2Initial = this.corner2
        this.side = this.pointSideOfVector(this.corner3, sub(this.corner2, this.corner1), this.corner1)
      } else {
        this.ctl.drawDirectionAtCursor(p, this.center)
        this.corner1 = p
        this.corner3 = sub(this.center, sub(p, this.center))
        const d = sub(p, this.center), perpendicular: XY = [-d[1], d[0]]
        this.corner2 = add(this.center, perpendicular); this.corner4 = sub(this.center, perpendicular)
        this.angle123 = pi / 2; this.angle412 = pi / 2
        this.side = this.pointSideOfVector(this.corner2, sub(this.corner3, this.corner1), this.corner1)
      }
      if (this.roundCorners) { this.length = len(sub(this.corner2, this.corner1)); this.width = len(sub(this.corner4, this.corner1)); this.radius = Math.min(this.length, this.width) / 6 }
      else this.radius = 0
      this.drawShape()
      this.ctl.drawWidthHeightAtCursor(p, this.length, this.width)
      this.seekAndRender(this.sug[1], p, [0, 0])
    } else if (this.state === 2) {
      if (this.twoCorner) {
        if (this.roundCorners) { this.calculateRadius(p); this.ctl.drawDoubleAtCursor(p, this.radius) }
        else { this.calculateThickness(p); this.ctl.drawDoubleAtCursor(p, this.thickness) } // a frame
      } else {
        const angleOf2 = (a: XY, b: XY) => { const l = len(a) * len(b); return Math.abs(l) > CONFUSION ? Math.acos(dot(a, b) / l) : null }
        if (this.method === 2) {
          this.corner2 = this.corner2Initial
          this.corner3 = p
          if (this.side === this.pointSideOfVector(this.corner3, sub(this.corner2, this.corner1), this.corner1)) { this.corner4 = add(this.corner1, sub(this.corner3, this.corner2)); this.cornersReversed = false }
          else { this.corner4 = this.corner2; this.corner2 = add(this.corner1, sub(this.corner3, this.corner4)); this.cornersReversed = true }
          const a = angleOf2(sub(this.corner1, this.corner2), sub(this.corner3, this.corner2))
          if (a !== null) this.angle123 = a
          this.angle412 = pi - this.angle123
        } else {
          this.corner2 = p
          this.corner4 = sub(this.center, sub(p, this.center))
          this.cornersReversed = false
          if (this.side !== this.pointSideOfVector(this.corner2, sub(this.corner3, this.corner1), this.corner1)) { this.corner4 = p; this.corner2 = sub(this.center, sub(p, this.center)); this.cornersReversed = true }
          const a = angleOf2(sub(this.corner4, this.corner1), sub(this.corner2, this.corner1))
          if (a !== null) this.angle412 = a
          this.angle123 = pi - this.angle412
        }
        const c412 = Math.cos(this.angle412), c123 = Math.cos(this.angle123)
        this.radius = this.roundCorners ? (Math.min(this.length, this.width) / 6) * Math.min(Math.sqrt(1 - c412 * c412), Math.sqrt(1 - c123 * c123)) : 0
        this.ctl.drawWidthHeightAtCursor(p, this.length, this.width)
      }
      this.drawShape()
      if (!this.twoCorner) this.seekAndRender(this.sug[2], p, [0, 0])
    } else if (this.state === 3) {
      if (this.twoCorner || !this.roundCorners) { this.calculateThickness(p); this.ctl.drawDoubleAtCursor(p, this.thickness) }
      else { this.calculateRadius(p); this.ctl.drawDoubleAtCursor(p, this.radius) }
      this.drawShape()
    } else if (this.state === 4) {
      this.calculateThickness(p); this.ctl.drawDoubleAtCursor(p, this.thickness)
      this.drawShape()
    }
  }
  protected executeCommands() {
    this.firstCurve = S.highestCurveIndex() + 1
    this.createShape(false)
    if (!this.shapeGeometry.length) throw new Error('Failed to add box: Cannot create a rectangle with zero length or width')
    S.openCommand('Add sketch box')
    this.addShape()
    S.commitCommand()
    this.thickness = 0
  }
  protected generateAutoConstraints() {
    const fc = this.firstCurve, rounded = this.radius > CONFUSION, [ac1, ac2, ac3] = this.sug
    if (this.method === 0) {
      if (rounded) { this.onElement(ac1, this.constructionPointOneId, START); this.onElement(ac2, this.constructionPointTwoId, START) }
      else { this.onElement(ac1, fc, START); this.onElement(ac2, fc + 1, END) }
    } else if (this.method === 1) {
      this.onElement(ac1, this.centerPointId, START)
      if (rounded) this.onElement(ac2, this.constructionPointOneId, START); else this.onElement(ac2, fc + 1, END)
    } else if (this.method === 2) {
      if (rounded) { this.onElement(ac1, this.constructionPointOneId, START); this.onElement(ac2, this.constructionPointTwoId, START); this.onElement(ac3, this.constructionPointThreeId, START) }
      else { this.onElement(ac1, fc, START); this.onElement(ac2, this.cornersReversed ? fc + 3 : fc + 1, START); this.onElement(ac3, fc + 2, START) }
    } else {
      this.onElement(ac1, this.centerPointId, START)
      if (rounded) { this.onElement(ac2, this.constructionPointOneId, START); this.onElement(ac3, this.constructionPointTwoId, START) }
      else { this.onElement(ac2, fc, START); this.onElement(ac3, this.cornersReversed ? fc + 3 : fc + 1, START) }
    }
    this.removeRedundantAutoConstraints()
  }
  protected angleSnappingControl() {
    if (this.method === 2 && this.state === 1) S.setAngleSnapping(true, this.corner1)
    else if (this.method === 3 && this.state === 1) S.setAngleSnapping(true, this.center)
    else if (this.method === 2 && this.state === 2) S.setAngleSnapping(true, this.cornersReversed ? this.corner4 : this.corner2)
    else if (this.method === 3 && this.state === 2) S.setAngleSnapping(true, this.corner1)
    else S.setAngleSnapping(false)
  }
  protected canGoToNextMode() { return !(this.state === 1 && !this.updateRectangleMetrics()) }
  /** onButtonPressed: without rounded corners or a frame the shape is done after its corners. */
  protected onButtonPressed(p: XY) {
    this.update(p)
    if (!this.canGoToNextMode()) return
    const s = this.state, r = this.roundCorners, f = this.makeFrame, END_STATE = this.states
    if (this.twoCorner) {
      if (s === 1 && !r && !f) this.setState(END_STATE)
      else if ((s === 2 && r && !f) || (s === 2 && !r && f)) this.setState(END_STATE)
      else if (s === 3) this.setState(END_STATE)
      else this.setState(s + 1)
    } else {
      if (s === 2 && !r && !f) this.setState(END_STATE)
      else if ((s === 3 && r && !f) || (s === 3 && !r && f)) this.setState(END_STATE)
      else this.setState(s + 1)
    }
  }
  protected onReset() { this.thickness = 0; this.lengthSign = 0; this.widthSign = 0 }

  protected createShape(onlyOutline: boolean) {
    this.shapeGeometry = []
    let vecL = sub(this.corner2, this.corner1), vecW = sub(this.corner4, this.corner1)
    if (!this.updateRectangleMetrics()) return
    vecL = mul(vecL, 1 / this.length); vecW = mul(vecW, 1 / this.width)
    let L1 = this.radius, L2 = this.radius
    const c123 = Math.cos(this.angle123 / 2), c412 = Math.cos(this.angle412 / 2)
    if (c123 !== 1 && c412 !== 1) { L1 = this.radius / Math.sqrt(1 - c123 * c123); L2 = this.radius / Math.sqrt(1 - c412 * c412) }
    this.createFirstRectangleGeometries(vecL, vecW, L1, L2)
    const thicknessNotZero = Math.abs(this.thickness) > CONFUSION
    const negThicknessEqualRadius = Math.abs(this.radius + this.thickness) < CONFUSION
    if (this.makeFrame && this.state !== 1 && thicknessNotZero) this.createSecondRectangleGeometries(vecL, vecW, L1, L2)
    if (!onlyOutline) {
      this.shapeConstraints = []
      if (this.radius > CONFUSION) this.finishOblongCreation(thicknessNotZero, negThicknessEqualRadius)
      else this.finishRectangleCreation(thicknessNotZero) // the plain rectangles and frames
    }
  }
  private updateRectangleMetrics(): boolean {
    const vecL = sub(this.corner2, this.corner1), vecW = sub(this.corner4, this.corner1)
    this.length = len(vecL); this.width = len(vecW); this.angle = angleOf(vecL)
    const fin = (p: XY) => Number.isFinite(p[0]) && Number.isFinite(p[1])
    const nonDegenerate = (a: number) => Number.isFinite(a) && Math.abs(a) % Math.PI >= CONFUSION
    return fin(this.corner1) && fin(this.corner2) && fin(this.corner3) && fin(this.corner4) && Number.isFinite(this.length) && Number.isFinite(this.width)
      && Number.isFinite(this.angle) && this.length >= CONFUSION && this.width >= CONFUSION && nonDegenerate(this.angle123) && nonDegenerate(this.angle412)
  }
  private createFirstRectangleGeometries(vecL: XY, vecW: XY, L1: number, L2: number) {
    const c123 = Math.cos(this.angle123 / 2), c412 = Math.cos(this.angle412 / 2)
    this.shapeGeometry.push(
      this.line(add(this.corner1, mul(vecL, L2 * c412)), sub(this.corner2, mul(vecL, L1 * c123))),
      this.line(add(this.corner2, mul(vecW, L1 * c123)), sub(this.corner3, mul(vecW, L2 * c412))),
      this.line(sub(this.corner3, mul(vecL, L2 * c412)), add(this.corner4, mul(vecL, L1 * c123))),
      this.line(sub(this.corner4, mul(vecW, L1 * c123)), add(this.corner1, mul(vecW, L2 * c412))))
    if (this.roundCorners && this.radius > CONFUSION) {
      // the centres, which a rounded frame with no inner radius needs later
      const end = this.angle - Math.PI / 2, b1 = normalize(add(vecL, vecW)), b2 = normalize(sub(vecL, vecW))
      this.center1 = add(this.corner1, mul(b1, L2)); this.center2 = sub(this.corner2, mul(b2, L1))
      this.center3 = sub(this.corner3, mul(b1, L2)); this.center4 = add(this.corner4, mul(b2, L1))
      const r = this.radius
      this.shapeGeometry.push(
        this.arc(this.center1, end - Math.PI + this.angle412, end, r),
        this.arc(this.center2, end, end - Math.PI - this.angle123, r),
        this.arc(this.center3, end + this.angle412, end - Math.PI, r),
        this.arc(this.center4, end - Math.PI, end - this.angle123, r))
    }
  }
  private createSecondRectangleGeometries(vecL: XY, vecW: XY, L1: number, L2: number) {
    const end = this.angle - Math.PI / 2
    if (this.radius < CONFUSION) this.radiusFrame = 0
    else { this.radiusFrame = this.radius + this.thickness; if (this.radiusFrame < 0) this.radiusFrame = 0 }
    const vecLF = sub(this.frameCorner2, this.frameCorner1), vecWF = sub(this.frameCorner4, this.frameCorner1)
    const lengthF = len(vecLF), widthF = len(vecWF)
    let L1F = 0, L2F = 0
    if (this.radius > CONFUSION) { L1F = (L1 * this.radiusFrame) / this.radius; L2F = (L2 * this.radiusFrame) / this.radius }
    const c123 = Math.cos(this.angle123 / 2), c412 = Math.cos(this.angle412 / 2)
    const uL = mul(vecLF, 1 / lengthF), uW = mul(vecWF, 1 / widthF)
    this.shapeGeometry.push(
      this.line(add(this.frameCorner1, mul(uL, L2F * c412)), sub(this.frameCorner2, mul(uL, L1F * c123))),
      this.line(add(this.frameCorner2, mul(uW, L1F * c123)), sub(this.frameCorner3, mul(uW, L2F * c412))),
      this.line(sub(this.frameCorner3, mul(uL, L2F * c412)), add(this.frameCorner4, mul(uL, L1F * c123))),
      this.line(sub(this.frameCorner4, mul(uW, L1F * c123)), add(this.frameCorner1, mul(uW, L2F * c412))))
    if (this.roundCorners && this.radiusFrame > CONFUSION) {
      const b1 = normalize(add(vecL, vecW)), b2 = normalize(sub(vecL, vecW)), r = this.radiusFrame
      this.shapeGeometry.push(
        this.arc(add(this.frameCorner1, mul(b1, L2F)), end - Math.PI + this.angle412, end, r),
        this.arc(sub(this.frameCorner2, mul(b2, L1F)), end, end - Math.PI - this.angle123, r),
        this.arc(sub(this.frameCorner3, mul(b1, L2F)), end + this.angle412, end - Math.PI, r),
        this.arc(add(this.frameCorner4, mul(b2, L1F)), end - Math.PI, end - this.angle123, r))
    }
  }
  private finishOblongCreation(thicknessNotZero: boolean, negThicknessEqualRadius: boolean) {
    const fc = this.firstCurve
    this.addTangentCoincidences(fc)
    this.addAlignmentConstraints()
    this.addArcEqualities()
    if (thicknessNotZero) {
      // 1: -thickness = radius: the inner rectangle is plain, its corners on the outer arcs' centres; 2: -thickness >
      // radius: plain, held by construction lines; 3: otherwise the inner rectangle is rounded too
      if (this.radiusFrame < CONFUSION) {
        this.addRectangleCoincidences(fc + 8)
        if (negThicknessEqualRadius) this.finishOblongFrameCase1()
        else this.finishOblongFrameCase2()
      } else this.finishOblongFrameCase3()
    }
    if (this.method === 2) this.finishOblongThreePoints(thicknessNotZero, negThicknessEqualRadius)
    else if (this.method === 3) this.finishOblongCenterAnd3Points(thicknessNotZero, negThicknessEqualRadius)
    else if (this.method === 1) this.finishOblongCenterAndCorner(thicknessNotZero, negThicknessEqualRadius)
    else this.finishOblongDiagonal(thicknessNotZero, negThicknessEqualRadius)
  }
  private finishOblongFrameCase1() {
    const fc = this.firstCurve
    for (let k = 0; k < 4; k++) this.shapeCon('Coincident', fc + 8 + k, START, fc + 4 + k, MID)
  }
  private finishOblongFrameCase2() {
    const fc = this.firstCurve
    this.addFrameAlignmentConstraints(fc + 8)
    const centers = [this.center1, this.center2, this.center3, this.center4], frames = [this.frameCorner1, this.frameCorner2, this.frameCorner3, this.frameCorner4]
    for (let k = 0; k < 4; k++) this.shapeGeometry.push(this.line(centers[k], frames[k], true))
    for (let k = 0; k < 4; k++) { this.shapeCon('Coincident', fc + 12 + k, START, fc + 4 + k, MID); this.shapeCon('Coincident', fc + 12 + k, END, fc + 8 + k, START) }
    for (let k = 0; k < 3; k++) this.shapeCon('Perpendicular', fc + 12 + k, NONE, fc + 13 + k)
  }
  private finishOblongFrameCase3() {
    const fc = this.firstCurve
    this.addTangentCoincidences(fc + 8)
    for (let k = 0; k < 4; k++) this.shapeCon('Coincident', fc + 4 + k, MID, fc + 12 + k, MID)
    this.addFrameAlignmentConstraints(fc + 8, false)
  }
  /** The construction points' ids: after the 8 curves, the frame's 4 lines (and 4 more curves unless case 1). */
  private oblongPointsAt(thicknessNotZero: boolean, negThicknessEqualRadius: boolean) {
    return this.firstCurve + (thicknessNotZero ? (negThicknessEqualRadius ? 12 : 16) : 8)
  }
  private finishOblongThreePoints(thicknessNotZero: boolean, negThicknessEqualRadius: boolean) {
    const fc = this.firstCurve, at = this.oblongPointsAt(thicknessNotZero, negThicknessEqualRadius)
    this.constructionPointOneId = at; this.constructionPointTwoId = at + 1; this.constructionPointThreeId = at + 2
    this.shapeGeometry.push(this.point(this.corner1, true))
    if (!this.cornersReversed) {
      this.shapeGeometry.push(this.point(this.corner2, true))
      this.shapeCon('PointOnObject', this.constructionPointTwoId, START, fc); this.shapeCon('PointOnObject', this.constructionPointTwoId, START, fc + 1)
    } else {
      this.shapeGeometry.push(this.point(this.corner4, true))
      this.shapeCon('PointOnObject', this.constructionPointTwoId, START, fc + 2); this.shapeCon('PointOnObject', this.constructionPointTwoId, START, fc + 3)
    }
    this.shapeGeometry.push(this.point(this.corner3, true))
    this.shapeCon('PointOnObject', this.constructionPointOneId, START, fc); this.shapeCon('PointOnObject', this.constructionPointOneId, START, fc + 3)
    this.shapeCon('PointOnObject', this.constructionPointThreeId, START, fc + 1); this.shapeCon('PointOnObject', this.constructionPointThreeId, START, fc + 2)
  }
  private finishOblongCenterAnd3Points(thicknessNotZero: boolean, negThicknessEqualRadius: boolean) {
    const fc = this.firstCurve, at = this.oblongPointsAt(thicknessNotZero, negThicknessEqualRadius)
    this.constructionPointOneId = at; this.constructionPointTwoId = at + 1; this.centerPointId = at + 2
    this.shapeGeometry.push(this.point(this.corner1, true))
    if (!this.cornersReversed) {
      this.shapeGeometry.push(this.point(this.corner2, true))
      this.shapeCon('PointOnObject', this.constructionPointTwoId, START, fc); this.shapeCon('PointOnObject', this.constructionPointTwoId, START, fc + 1)
    } else {
      this.shapeGeometry.push(this.point(this.corner4, true))
      this.shapeCon('PointOnObject', this.constructionPointTwoId, START, fc + 2); this.shapeCon('PointOnObject', this.constructionPointTwoId, START, fc + 3)
    }
    this.shapeGeometry.push(this.point(this.center, true))
    this.shapeCon('Symmetric', fc + 2, START, fc, START, this.centerPointId, START)
    this.shapeCon('PointOnObject', this.constructionPointOneId, START, fc); this.shapeCon('PointOnObject', this.constructionPointOneId, START, fc + 3)
  }
  private finishOblongCenterAndCorner(thicknessNotZero: boolean, negThicknessEqualRadius: boolean) {
    const fc = this.firstCurve, at = this.oblongPointsAt(thicknessNotZero, negThicknessEqualRadius)
    this.constructionPointOneId = at; this.centerPointId = at + 1
    this.shapeGeometry.push(this.point(this.corner3, true), this.point(this.center, true))
    this.shapeCon('Symmetric', fc + 2, START, fc, START, this.centerPointId, START)
    this.shapeCon('PointOnObject', this.constructionPointOneId, START, fc + 1); this.shapeCon('PointOnObject', this.constructionPointOneId, START, fc + 2)
  }
  private finishOblongDiagonal(thicknessNotZero: boolean, negThicknessEqualRadius: boolean) {
    const fc = this.firstCurve, at = this.oblongPointsAt(thicknessNotZero, negThicknessEqualRadius)
    this.constructionPointOneId = at; this.constructionPointTwoId = at + 1
    this.shapeGeometry.push(this.point(this.corner1, true), this.point(this.corner3, true))
    this.shapeCon('PointOnObject', this.constructionPointOneId, START, fc); this.shapeCon('PointOnObject', this.constructionPointOneId, START, fc + 3)
    this.shapeCon('PointOnObject', this.constructionPointTwoId, START, fc + 1); this.shapeCon('PointOnObject', this.constructionPointTwoId, START, fc + 2)
  }
  private addTangentCoincidences(g: number) {
    this.shapeCon('Tangent', g, START, g + 4, END); this.shapeCon('Tangent', g, END, g + 5, START)
    this.shapeCon('Tangent', g + 1, START, g + 5, END); this.shapeCon('Tangent', g + 1, END, g + 6, START)
    this.shapeCon('Tangent', g + 2, START, g + 6, END); this.shapeCon('Tangent', g + 2, END, g + 7, START)
    this.shapeCon('Tangent', g + 3, START, g + 7, END); this.shapeCon('Tangent', g + 3, END, g + 4, START)
  }
  private addArcEqualities() {
    const fc = this.firstCurve
    this.shapeCon('Equal', fc + 4, NONE, fc + 5); this.shapeCon('Equal', fc + 5, NONE, fc + 6); this.shapeCon('Equal', fc + 6, NONE, fc + 7)
  }
  private finishRectangleCreation(thicknessNotZero: boolean) {
    this.addRectangleCoincidences(this.firstCurve)
    this.addAlignmentConstraints()
    if (thicknessNotZero) this.finishRectangleFrameCreation()
    if (this.method === 1 || this.method === 3) this.finishCenteredRectangleCreation(thicknessNotZero)
  }
  private addRectangleCoincidences(g: number) {
    for (let k = 0; k < 4; k++) this.shapeCon('Coincident', g + k, END, g + ((k + 1) % 4), START)
  }
  /** Which sides are horizontal depends on which way the diagonal runs; a rectangle at an angle gets parallels. */
  private alignmentTypes(): [ConstraintType, ConstraintType] {
    return sgn(this.corner3[0] - this.corner1[0]) * sgn(this.corner3[1] - this.corner1[1]) < 0 ? ['Vertical', 'Horizontal'] : ['Horizontal', 'Vertical']
  }
  private addAlignmentConstraints() {
    const fc = this.firstCurve, [ta, tb] = this.alignmentTypes()
    if (Math.abs(this.angle) < CONFUSION || this.twoCorner) {
      this.shapeCon(ta, fc); this.shapeCon(ta, fc + 2); this.shapeCon(tb, fc + 1); this.shapeCon(tb, fc + 3)
    } else {
      this.shapeCon('Parallel', fc, NONE, fc + 2); this.shapeCon('Parallel', fc + 1, NONE, fc + 3)
      if (Math.abs(this.angle123 - Math.PI / 2) < CONFUSION) this.shapeCon('Perpendicular', fc, NONE, fc + 1)
    }
  }
  private finishRectangleFrameCreation() {
    const fc = this.firstCurve
    this.addRectangleCoincidences(fc + 4)
    this.addFrameAlignmentConstraints(fc + 4)
    this.addRectangleFrameConstructionLines()
  }
  private addFrameAlignmentConstraints(g: number, addLast = true) {
    const fc = this.firstCurve, [ta, tb] = this.alignmentTypes()
    if (Math.abs(this.angle) < CONFUSION || this.twoCorner) {
      this.shapeCon(ta, g); this.shapeCon(ta, g + 2); this.shapeCon(tb, g + 1)
      if (addLast) this.shapeCon(tb, g + 3)
    } else {
      this.shapeCon('Parallel', g, NONE, g + 2); this.shapeCon('Parallel', g + 1, NONE, g + 3); this.shapeCon('Parallel', fc, NONE, g)
      if (addLast) this.shapeCon('Parallel', fc + 1, NONE, g + 1)
    }
  }
  private addRectangleFrameConstructionLines() {
    const fc = this.firstCurve
    const corners = [this.corner1, this.corner2, this.corner3, this.corner4], frames = [this.frameCorner1, this.frameCorner2, this.frameCorner3, this.frameCorner4]
    for (let k = 0; k < 4; k++) this.shapeGeometry.push(this.line(corners[k], frames[k], true))
    for (let k = 0; k < 4; k++) { this.shapeCon('Coincident', fc + 8 + k, START, fc + k, START); this.shapeCon('Coincident', fc + 8 + k, END, fc + 4 + k, START) }
    for (let k = 0; k < 3; k++) this.shapeCon('Perpendicular', fc + 8 + k, NONE, fc + 9 + k)
  }
  private finishCenteredRectangleCreation(thicknessNotZero: boolean) {
    const fc = this.firstCurve
    this.centerPointId = fc + (thicknessNotZero ? 12 : 4)
    this.shapeGeometry.push(this.point(this.center, true))
    this.shapeCon('Symmetric', fc + 2, START, fc, START, this.centerPointId, START)
  }
  /** getPointSideOfVector: which side of the line through pointOnVector along separatingVector the point lies (0 on it). */
  private pointSideOfVector(pointToCheck: XY, separatingVector: XY, pointOnVector: XY) {
    const second = add(pointOnVector, separatingVector)
    const d = (pointToCheck[0] - pointOnVector[0]) * (second[1] - pointOnVector[1]) - (pointToCheck[1] - pointOnVector[1]) * (second[0] - pointOnVector[0])
    return Math.abs(d) < CONFUSION ? 0 : d < 0 ? -1 : 1
  }
  private calculateRadius(p: XY) {
    const u = normalize(sub(this.corner2, this.corner1)), v = normalize(sub(this.corner4, this.corner1)), e = sub(p, this.corner1)
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
  private calculateThickness(p: XY) {
    const u = normalize(sub(this.corner2, this.corner1)), v = normalize(sub(this.corner4, this.corner1)), e = sub(p, this.corner1)
    const det = u[0] * v[1] - u[1] * v[0]
    const du = (v[1] * e[0] - v[0] * e[1]) / det, dv = (-u[1] * e[0] + u[0] * e[1]) / det
    const inL = du > 0 && du < this.length, inW = dv > 0 && dv < this.width
    const nearL = Math.min(Math.abs(du), Math.abs(this.length - du)), nearW = Math.min(Math.abs(dv), Math.abs(this.width - dv))
    let t: number
    if (inL && !inW) t = nearW
    else if (inW && !inL) t = nearL
    else if (inL && inW) t = -Math.min(nearL, nearW)
    else t = Math.max(nearL, nearW)
    this.frameCorner1 = sub(sub(this.corner1, mul(u, t)), mul(v, t))
    this.frameCorner2 = sub(add(this.corner2, mul(u, t)), mul(v, t))
    this.frameCorner3 = add(add(this.corner3, mul(u, t)), mul(v, t))
    this.frameCorner4 = add(sub(this.corner4, mul(u, t)), mul(v, t))
    this.thickness = t * Math.sin(this.angle412)
  }

  // the controller's specialisations (DSHRectangleController)
  isWidgetVisible() { return true }
  toolWidgetText() { return 'Rectangle Parameters' }
  toolIcon() { return 'Sketcher_CreateRectangle' }
  ovpSpec(): OvpSpec { return { ovps: this.twoCorner ? 6 : 8, widget: { parameters: 0, checkboxes: 2, comboboxes: 1, lineEdits: 0 }, firstComboIsMethod: true } }
  ovpState(i: number) {
    const END_STATE = this.states
    if (this.twoCorner) {
      if (i < 2) return 0
      if (i < 4) return 1
      if (i === OVP.Fifth) return this.roundCorners ? 2 : END_STATE
      return this.makeFrame ? (this.roundCorners ? 3 : 2) : END_STATE
    }
    if (i < 2) return 0
    if (i < 4) return 1
    if (i < 6) return 2
    if (i === OVP.Seventh) return this.roundCorners ? 3 : END_STATE
    return this.makeFrame ? (this.roundCorners ? 4 : 3) : END_STATE
  }
  configureToolWidget(c: Controller) {
    if (!c.init) {
      c.setComboboxElements(0, ['Corner, width, height', 'Center, width, height', '3 corners', 'Center, 2 corners'])
      c.setCheckboxLabel(0, 'Rounded corners (U)')
      c.setCheckboxToolTip(0, 'Create a rectangle with rounded corners.')
      c.syncCheckboxToHandler(0, this.roundCorners)
      c.setCheckboxLabel(1, 'Frame (J)')
      c.setCheckboxToolTip(1, 'Create two rectangles with a constant offset.')
      c.syncCheckboxToHandler(1, this.makeFrame)
      const k = this.isConstructionMode() ? '_Constr' : ''
      c.setComboboxItemIcon(0, 0, `Sketcher_CreateRectangle${k}`); c.setComboboxItemIcon(0, 1, `Sketcher_CreateRectangle_Center${k}`)
      c.setComboboxItemIcon(0, 2, `Sketcher_CreateRectangle3Points${k}`); c.setComboboxItemIcon(0, 3, `Sketcher_CreateRectangle3Points_Center${k}`)
      c.setCheckboxIcon(0, `Sketcher_CreateOblong${k}`); c.setCheckboxIcon(1, `Sketcher_CreateFrame${k}`)
    }
    const o = c.onViewParameters
    o[OVP.First].setLabelType('DISTANCEX'); o[OVP.Second].setLabelType('DISTANCEY')
    if (this.twoCorner) {
      o[OVP.Third].setLabelType('DISTANCEX', 'Dimensioning'); o[OVP.Fourth].setLabelType('DISTANCEY', 'Dimensioning')
      o[OVP.Fifth].setLabelType('RADIUS', 'Dimensioning'); o[OVP.Sixth].setLabelType('DISTANCE', 'Dimensioning')
    } else {
      if (this.method === 2) { o[OVP.Third].setLabelType('DISTANCE', 'Dimensioning'); o[OVP.Fourth].setLabelType('ANGLE', 'Dimensioning') }
      else { o[OVP.Third].setLabelType('DISTANCEX'); o[OVP.Fourth].setLabelType('DISTANCEY') }
      o[OVP.Fifth].setLabelType('DISTANCE', 'Dimensioning'); o[OVP.Sixth].setLabelType('ANGLE', 'Dimensioning')
      o[OVP.Seventh].setLabelType('RADIUS', 'Dimensioning'); o[OVP.Eighth].setLabelType('DISTANCE', 'Dimensioning')
    }
  }
  adaptDrawingToCheckboxChange(_c: Controller, i: number, v: boolean) {
    if (i === 0) this.roundCorners = v
    else if (i === 1) this.makeFrame = v
    this.updateCursor()
  }
  doEnforceControlParameters(c: Controller, p: XY): XY {
    const o = c.onViewParameters
    let [x, y] = p
    const deg = (v: number) => (v * Math.PI) / 180
    /** A thickness at or beyond half the rectangle cannot be: the parameter is unset. */
    const thicknessAt = (k: number, diagonal: boolean): boolean => {
      const prm = o[k]
      if (!prm.isSet) return false
      const t = prm.getValue()
      if (t <= -Math.min(this.width, this.length) / 2 && prm.hasFinishedEditing) { c.unsetOnViewParameter(prm); return true }
      const u = normalize(sub(this.corner2, this.corner1)), v = normalize(sub(this.corner4, this.corner1))
      if (!diagonal) { [x, y] = sub(sub(this.corner1, mul(u, t)), mul(v, t)); return false }
      const dir = normalize(add(u, v)), half = getAngle(u, v) / 2
      let sinAngle = Math.abs(Math.sin(half))
      if (sinAngle < CONFUSION) sinAngle = 1 // no division by 0
      ;[x, y] = sub(this.corner1, mul(dir, t / sinAngle))
      return false
    }
    switch (this.state) {
      case 0:
        if (o[OVP.First].isSet) x = o[OVP.First].getValue()
        if (o[OVP.Second].isSet) y = o[OVP.Second].getValue()
        break
      case 1:
        if (this.twoCorner) {
          const third = o[OVP.Third], fourth = o[OVP.Fourth]
          if (third.isSet) {
            const length = third.getValue()
            if (Math.abs(length) < CONFUSION && third.hasFinishedEditing) { c.unsetOnViewParameter(third); this.lengthSign = 0; return [x, y] }
            if (this.method === 0) {
              if (this.lengthSign === 0) this.lengthSign = x - this.corner1[0] >= 0 ? 1 : -1
              x = this.corner1[0] + this.lengthSign * length
            } else x = this.center[0] + length / 2
          }
          if (fourth.isSet) {
            const width = fourth.getValue()
            if (Math.abs(width) < CONFUSION && fourth.hasFinishedEditing) { c.unsetOnViewParameter(fourth); this.widthSign = 0; return [x, y] }
            if (this.method === 0) {
              if (this.widthSign === 0) this.widthSign = y - this.corner1[1] >= 0 ? 1 : -1
              y = this.corner1[1] + this.widthSign * width
            } else y = this.center[1] + width / 2
          }
        } else if (this.method === 2) {
          let dir = sub([x, y], this.corner1)
          if (len(dir) < CONFUSION) dir = [1, dir[1]] // a null direction defaults to (1, 0)
          let length = len(dir)
          const third = o[OVP.Third], fourth = o[OVP.Fourth]
          if (third.isSet) {
            length = third.getValue()
            if (length < CONFUSION && third.hasFinishedEditing) { c.unsetOnViewParameter(third); return [x, y] }
            ;[x, y] = add(this.corner1, mul(normalize(dir), length))
          }
          if (fourth.isSet) { const a = deg(fourth.getValue()); x = this.corner1[0] + Math.cos(a) * length; y = this.corner1[1] + Math.sin(a) * length }
        } else {
          const third = o[OVP.Third], fourth = o[OVP.Fourth]
          if (third.isSet) x = third.getValue()
          if (fourth.isSet) y = fourth.getValue()
          if (third.hasFinishedEditing && fourth.hasFinishedEditing && len(sub([x, y], this.center)) < CONFUSION) { c.unsetOnViewParameter(third); c.unsetOnViewParameter(fourth) }
        }
        break
      case 2:
        if (this.twoCorner) {
          if (this.roundCorners) {
            if (o[OVP.Fifth].isSet) [x, y] = add(this.corner1, mul(normalize(sub(this.corner2, this.corner1)), o[OVP.Fifth].getValue()))
          } else if (thicknessAt(OVP.Sixth, false)) return [x, y]
        } else if (this.method === 2) {
          let dir = sub([x, y], this.corner2Initial)
          if (len(dir) < CONFUSION) dir = [1, dir[1]]
          let width = len(dir)
          const fifth = o[OVP.Fifth], sixth = o[OVP.Sixth]
          if (fifth.isSet) {
            width = fifth.getValue()
            if (width < CONFUSION && fifth.hasFinishedEditing) { c.unsetOnViewParameter(fifth); return [x, y] }
            ;[x, y] = add(this.corner2Initial, mul(normalize(dir), width))
          }
          if (sixth.isSet) {
            const a = deg(sixth.getValue())
            if (a % Math.PI < CONFUSION && sixth.hasFinishedEditing) { c.unsetOnViewParameter(sixth); return [x, y] }
            const sign1 = this.pointSideOfVector([x, y], sub(this.corner2Initial, this.corner1), this.corner1)
            const sign = this.side !== sign1 ? 1 : -1
            const a123 = angleOf(sub(this.corner2Initial, this.corner1)) + Math.PI + sign * a
            x = this.corner2Initial[0] + Math.cos(a123) * width; y = this.corner2Initial[1] + Math.sin(a123) * width
          }
        } else {
          let dir = sub([x, y], this.corner1)
          if (len(dir) < CONFUSION) dir = [1, dir[1]]
          let width = len(dir)
          const fifth = o[OVP.Fifth], sixth = o[OVP.Sixth]
          if (fifth.isSet) {
            width = fifth.getValue()
            if (width < CONFUSION && fifth.hasFinishedEditing) { c.unsetOnViewParameter(fifth); return [x, y] }
            ;[x, y] = add(this.corner1, mul(normalize(dir), width))
          }
          if (sixth.isSet) {
            const cc = deg(sixth.getValue())
            if (cc % Math.PI < CONFUSION && sixth.hasFinishedEditing) { c.unsetOnViewParameter(sixth); return [x, y] }
            const a = Math.asin((width * Math.sin(Math.PI - cc)) / len(sub(this.corner3, this.corner1)))
            const sign1 = this.pointSideOfVector([x, y], sub(this.corner3, this.corner1), this.corner1)
            const sign = this.side !== sign1 ? 1 : -1
            const angle = angleOf(sub(this.center, this.corner1)) + sign * (cc - a)
            x = this.corner1[0] + Math.cos(angle) * width; y = this.corner1[1] + Math.sin(angle) * width
          }
        }
        break
      case 3:
        if (this.twoCorner) { if (thicknessAt(OVP.Sixth, false)) return [x, y] }
        else if (this.roundCorners) {
          if (o[OVP.Seventh].isSet) {
            const angleToUse = this.method === 3 ? this.angle123 / 2 : this.angle412 / 2
            const vecL = normalize(sub(this.corner2Initial, this.corner1))
            const L2 = o[OVP.Seventh].getValue() / Math.sqrt(1 - Math.cos(angleToUse) * Math.cos(angleToUse))
            ;[x, y] = add(this.corner1, mul(vecL, L2 * Math.cos(angleToUse)))
          }
        } else if (thicknessAt(OVP.Eighth, true)) return [x, y]
        break
      case 4:
        if (thicknessAt(OVP.Eighth, true)) return [x, y]
        break
    }
    return [x, y]
  }
  adaptParameters(c: Controller, p: XY) {
    // check boxes the handler changed (M to another method, …) are synchronised first, and that is all
    if (c.getCheckboxChecked(0) !== this.roundCorners) { c.syncCheckboxToHandler(0, this.roundCorners); return }
    if (c.getCheckboxChecked(1) !== this.makeFrame) { c.syncCheckboxToHandler(1, this.makeFrame); return }
    const o = c.onViewParameters
    switch (this.state) {
      case 0: {
        if (!o[OVP.First].isSet) c.setOnViewParameterValue(OVP.First, p[0])
        if (!o[OVP.Second].isSet) c.setOnViewParameterValue(OVP.Second, p[1])
        const sameSign = p[0] * p[1] > 0
        o[OVP.First].setLabelAutoDistanceReverse(!sameSign); o[OVP.Second].setLabelAutoDistanceReverse(sameSign)
        o[OVP.First].setPoints([0, 0], p); o[OVP.Second].setPoints([0, 0], p)
        break
      }
      case 1: {
        const third = o[OVP.Third], fourth = o[OVP.Fourth]
        if (this.twoCorner) {
          if (!third.isSet) c.setOnViewParameterValue(OVP.Third, this.cornersReversed ? this.width : this.length)
          if (!fourth.isSet) c.setOnViewParameterValue(OVP.Fourth, this.cornersReversed ? this.length : this.width)
          const start = this.corner1, vec = sub(p, start), sameSign = vec[0] * vec[1] > 0
          third.setLabelAutoDistanceReverse(sameSign); fourth.setLabelAutoDistanceReverse(!sameSign)
          third.setPoints(start, this.cornersReversed ? this.corner4 : this.corner2)
          fourth.setPoints(start, this.cornersReversed ? this.corner2 : this.corner4)
        } else if (this.method === 2) {
          if (!third.isSet) c.setOnViewParameterValue(OVP.Third, this.length)
          third.setPoints(this.corner4, this.corner3)
          if (!fourth.isSet) c.setOnViewParameterValue(OVP.Fourth, (this.angle * 180) / Math.PI, 'Angle')
          fourth.setPoints(this.corner1, [0, 0])
          fourth.setLabelRange(angleOf(sub(this.corner2, this.corner1)))
        } else {
          if (!third.isSet) c.setOnViewParameterValue(OVP.Third, p[0])
          if (!fourth.isSet) c.setOnViewParameterValue(OVP.Fourth, p[1])
          const sameSign = p[0] * p[1] > 0
          third.setLabelAutoDistanceReverse(!sameSign); fourth.setLabelAutoDistanceReverse(sameSign)
          third.setPoints([0, 0], p); fourth.setPoints([0, 0], p)
        }
        break
      }
      case 2: {
        if (this.twoCorner) {
          if (this.roundCorners) {
            if (!o[OVP.Fifth].isSet) c.setOnViewParameterValue(OVP.Fifth, this.radius)
            const center = this.center3
            let end = this.corner3
            if (this.radius !== 0) end = add(center, mul(normalize(sub(end, center)), this.radius))
            o[OVP.Fifth].setPoints(center, end)
          } else {
            if (!o[OVP.Sixth].isSet) c.setOnViewParameterValue(OVP.Sixth, this.thickness)
            o[OVP.Sixth].setPoints(this.corner3, [this.corner3[0], this.frameCorner3[1]])
          }
        } else if (this.method === 2) {
          o[OVP.Third].setPoints(this.corner4, this.corner3)
          const reversed = this.cornersReversed, fifth = o[OVP.Fifth], sixth = o[OVP.Sixth]
          if (!fifth.isSet) c.setOnViewParameterValue(OVP.Fifth, reversed ? this.length : this.width)
          fifth.setLabelAutoDistanceReverse(reversed)
          fifth.setPoints(this.corner1, reversed ? this.corner2 : this.corner4)
          if (!sixth.isSet) c.setOnViewParameterValue(OVP.Sixth, (this.angle123 * 180) / Math.PI, 'Angle')
          sixth.setPoints(reversed ? this.corner4 : this.corner2, [0, 0])
          sixth.setLabelStartAngle(reversed ? angleOf(sub(this.corner1, this.corner4)) : angleOf(sub(this.corner3, this.corner2)))
          sixth.setLabelRange(this.angle123)
        } else {
          const reversed = this.cornersReversed, fifth = o[OVP.Fifth], sixth = o[OVP.Sixth]
          if (!fifth.isSet) c.setOnViewParameterValue(OVP.Fifth, reversed ? this.width : this.length)
          fifth.setLabelAutoDistanceReverse(true)
          fifth.setPoints(this.corner1, reversed ? this.corner4 : this.corner2)
          if (!sixth.isSet) c.setOnViewParameterValue(OVP.Sixth, (this.angle412 * 180) / Math.PI, 'Angle')
          sixth.setPoints(this.corner1, [0, 0])
          sixth.setLabelStartAngle(angleOf(sub(this.corner2, this.corner1)))
          sixth.setLabelRange(this.angle412)
        }
        break
      }
      case 3: {
        if (this.twoCorner) {
          if (!o[OVP.Sixth].isSet) c.setOnViewParameterValue(OVP.Sixth, this.thickness)
          o[OVP.Sixth].setPoints(this.corner3, [this.corner3[0], this.frameCorner3[1]])
        } else if (this.roundCorners) {
          if (!o[OVP.Seventh].isSet) c.setOnViewParameterValue(OVP.Seventh, this.radius)
          const center = this.center3
          let end = this.corner3
          if (this.radius !== 0) end = add(center, mul(normalize(sub(end, center)), this.radius))
          o[OVP.Seventh].setPoints(center, end)
        } else {
          if (!o[OVP.Eighth].isSet) c.setOnViewParameterValue(OVP.Eighth, this.thickness)
          o[OVP.Eighth].setPoints(this.corner3, add(this.corner3, mul(normalize(sub(this.corner3, this.corner2)), this.thickness)))
        }
        break
      }
      case 4: {
        if (!o[OVP.Eighth].isSet) c.setOnViewParameterValue(OVP.Eighth, this.thickness)
        o[OVP.Eighth].setPoints(this.corner3, add(this.corner3, mul(normalize(sub(this.corner3, this.corner2)), this.thickness)))
        break
      }
    }
  }
  computeNextDrawSketchHandlerMode(c: Controller) {
    const o = c.onViewParameters, END_STATE = this.states
    switch (this.state) {
      case 0: if (o[OVP.First].hasFinishedEditing && o[OVP.Second].hasFinishedEditing) this.setNextState(1); break
      case 1:
        if (o[OVP.Third].hasFinishedEditing && o[OVP.Fourth].hasFinishedEditing) {
          if (!this.canGoToNextMode()) return
          this.setNextState(this.roundCorners || this.makeFrame || !this.twoCorner ? 2 : END_STATE)
        }
        break
      case 2:
        if (this.twoCorner) {
          if (this.roundCorners && o[OVP.Fifth].hasFinishedEditing) this.setNextState(this.makeFrame ? 3 : END_STATE)
          else if (this.makeFrame && o[OVP.Sixth].hasFinishedEditing) this.setNextState(END_STATE)
        } else if (o[OVP.Fifth].hasFinishedEditing && o[OVP.Sixth].hasFinishedEditing) this.setNextState(this.roundCorners || this.makeFrame ? 3 : END_STATE)
        break
      case 3:
        if (this.twoCorner) { if (o[OVP.Sixth].hasFinishedEditing) this.setNextState(END_STATE) }
        else if (this.roundCorners && o[OVP.Seventh].hasFinishedEditing) this.setNextState(this.makeFrame ? 4 : END_STATE)
        else if (this.makeFrame && o[OVP.Eighth].hasFinishedEditing) this.setNextState(END_STATE)
        break
      case 4: if (this.makeFrame && o[OVP.Eighth].hasFinishedEditing) this.setNextState(END_STATE); break
    }
  }
  /** DSHRectangleController::addConstraints, with no auto-constraints diagnosed yet (they come after): the first
   *  point's position, the sides' lengths (a Distance between the ends of opposite sides), the angles, the radius and
   *  the frame's thickness. */
  addConstraints(c: Controller) {
    const o = c.onViewParameters, fc = this.firstCurve, pi = Math.PI
    const reverse = this.method === 3 ? !this.cornersReversed : this.cornersReversed
    const x0 = o[OVP.First].getValue(), y0 = o[OVP.Second].getValue()
    let length = o[OVP.Third].getValue(), width = o[OVP.Fourth].getValue(), radius = o[OVP.Fifth].getValue(), thickness = o[OVP.Sixth].getValue()
    const x0set = o[OVP.First].isSet, y0set = o[OVP.Second].isSet
    let lengthSet = o[OVP.Third].isSet, widthSet = o[OVP.Fourth].isSet, radiusSet = o[OVP.Fifth].isSet, thicknessSet = o[OVP.Sixth].isSet
    const corner1x = o[OVP.Third].getValue(), corner1y = o[OVP.Fourth].getValue()
    const angle = (o[OVP.Fourth].getValue() * pi) / 180, innerAngle = (o[OVP.Sixth].getValue() * pi) / 180
    const corner1xSet = o[OVP.Third].isSet, corner1ySet = o[OVP.Fourth].isSet, angleSet = o[OVP.Fourth].isSet, innerAngleSet = o[OVP.Sixth].isSet
    if (this.method === 3) lengthSet = false
    if (!this.twoCorner) {
      width = o[OVP.Fifth].getValue(); radius = o[OVP.Seventh].getValue(); thickness = o[OVP.Eighth].getValue()
      widthSet = o[OVP.Fifth].isSet; radiusSet = o[OVP.Seventh].isSet; thicknessSet = o[OVP.Eighth].isSet
    }
    let firstPointId = fc
    if (this.method === 0 || this.method === 2) { if (this.radius > CONFUSION) firstPointId = this.constructionPointOneId }
    else firstPointId = this.centerPointId
    if (x0set) constraintToAttachment([firstPointId, START], V_AXIS_ID, x0)
    if (y0set) constraintToAttachment([firstPointId, START], H_AXIS_ID, y0)
    const sideDistance = (curveId: number, v: number) => S.addConstraint(constraint('Distance', curveId, START, curveId + 2, END, GEO_UNDEF, NONE, f6(Math.abs(v))))
    if (lengthSet) sideDistance(reverse ? fc : fc + 1, length)
    if (widthSet) sideDistance(reverse ? fc + 1 : fc, width)
    // no auto-constraint lands on the radius or the thickness: they can always be set
    const notRight = (a: number) => Math.abs((Math.abs(a) % pi) - pi / 2) > CONFUSION // a right angle is a Perpendicular already
    if (this.method === 2) {
      if (angleSet) constraintLineByAngle(fc, angle)
      if (innerAngleSet && notRight(innerAngle)) S.addConstraint(constraint('Angle', fc + 1, START, fc, END, GEO_UNDEF, NONE, f6(innerAngle)))
    } else if (this.method === 3) {
      if (corner1xSet) constraintToAttachment([fc, START], V_AXIS_ID, corner1x)
      if (corner1ySet) constraintToAttachment([fc, START], H_AXIS_ID, corner1y)
      if (innerAngleSet && notRight(innerAngle)) S.addConstraint(constraint('Angle', fc, START, fc + 3, END, GEO_UNDEF, NONE, f6(innerAngle)))
    }
    if (radiusSet && radius > CONFUSION) S.addConstraint(constraint('Radius', fc + 5, NONE, GEO_UNDEF, NONE, GEO_UNDEF, NONE, f6(radius)))
    // with -thickness = radius the inner corners sit on the outer arcs' centres: a thickness would be redundant
    const negThicknessEqualRadius = Math.abs(radius + thickness) < CONFUSION
    if (thicknessSet && !negThicknessEqualRadius) S.addConstraint(constraint('Distance', fc + (this.roundCorners ? 8 : 4), START, fc, NONE, GEO_UNDEF, NONE, f6(Math.abs(thickness))))
  }
  doConstructionMethodChanged() { S.updateHints() }
}

// ── Slot (DrawSketchHandlerSlot.h) ───────────────────────────────────────────────────────────────────────────────
/** Two arcs and two lines: the first centre, the second (length and angle), the width (the radius). ThreeSeekEnd.
 *  DSHSlotController: the first centre's X and Y, the length and angle, the radius; no widget shown. */
export class SlotHandler extends DefaultHandler {
  readonly toolName = 'DSH_Slot'
  protected readonly states = 3
  protected readonly autoConstraintSize = 2
  private startPoint: XY = [0, 0]; private secondPoint: XY = [0, 0]; private radius = 1; private length = 0; private angle = 0; private firstCurve = 0
  /** The direction taken when the angle is typed, so that the mouse does not flip the parameter (#23459). */
  private capturedDirection: XY = [0, 0]
  crosshair() { return 'Sketcher_Pointer_Slot' }
  hints() { return this.state > 2 ? [] : [this.hint(['%1 pick slot start point', '%1 pick slot end point', '%1 pick slot width'][this.state], [LMB])] }
  protected update(p: XY) {
    if (this.state === 0) { this.ctl.drawPositionAtCursor(p); this.startPoint = p; this.seekAndRender(this.sug[0], p, [0, 0]) }
    else if (this.state === 1) {
      this.ctl.drawDirectionAtCursor(p, this.startPoint)
      this.secondPoint = p
      this.angle = angleOf(sub(this.secondPoint, this.startPoint)); this.length = len(sub(this.secondPoint, this.startPoint))
      this.radius = this.length * 0.2 // a fifth of the length
      this.drawShape()
      this.seekAndRender(this.sug[1], p, sub(this.secondPoint, this.startPoint), 'vertexNoTangency')
    } else if (this.state === 2) {
      // between the centres the distance to the line through them, beyond them the distance to the nearer centre
      const L1 = len(sub(p, this.startPoint)), L2 = len(sub(p, this.secondPoint)), l = this.length
      if (L1 * L1 + l * l > L2 * L2 && L2 * L2 + l * l > L1 * L1) {
        const [s, e] = [this.startPoint, this.secondPoint]
        this.radius = Math.abs((e[1] - s[1]) * p[0] - (e[0] - s[0]) * p[1] + e[0] * s[1] - e[1] * s[0]) / l
      } else this.radius = Math.min(L1, L2)
      this.ctl.drawDoubleAtCursor(p, this.radius)
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
  protected executeCommands() { this.firstCurve = S.highestCurveIndex() + 1; S.openCommand('Add slot'); this.createShape(false); this.addShape(); S.commitCommand() }
  protected generateAutoConstraints() {
    // an alignment goes on the line, not on the arc
    let alignment = false
    for (const ac of this.sug[1]) if (['Horizontal', 'Vertical', 'Perpendicular', 'Parallel'].includes(ac.type)) { ac.geoId = this.firstCurve + 2; alignment = true }
    if (this.avoidRedundants && alignment) removeRedundantHorizontalVertical(this.sug[0], this.sug[1])
    this.onElement(this.sug[0], S.highestCurveIndex() - 3, MID)
    this.onElement(this.sug[1], S.highestCurveIndex() - 2, MID)
    this.removeRedundantAutoConstraints()
  }
  ovpSpec(): OvpSpec { return { ovps: 5, widget: { parameters: 0, checkboxes: 0, comboboxes: 0, lineEdits: 0 }, firstComboIsMethod: false } }
  ovpState(i: number) { return i < 2 ? 0 : i < 4 ? 1 : 2 }
  configureToolWidget(c: Controller) {
    const o = c.onViewParameters
    o[OVP.First].setLabelType('DISTANCEX'); o[OVP.Second].setLabelType('DISTANCEY')
    o[OVP.Third].setLabelType('DISTANCE', 'Dimensioning'); o[OVP.Fourth].setLabelType('ANGLE', 'Dimensioning'); o[OVP.Fifth].setLabelType('RADIUS', 'Dimensioning')
  }
  doEnforceControlParameters(c: Controller, p: XY): XY {
    const o = c.onViewParameters
    let [x, y] = p
    if (this.state === 0) {
      if (o[OVP.First].isSet) x = o[OVP.First].getValue()
      if (o[OVP.Second].isSet) y = o[OVP.Second].getValue()
    } else if (this.state === 1) {
      const third = o[OVP.Third], fourth = o[OVP.Fourth]
      let dir = sub([x, y], this.startPoint)
      if (len(dir) < CONFUSION) dir = [1, dir[1]] // a null direction defaults to (1, 0)
      if (fourth.isSet) { const a = (fourth.getValue() * Math.PI) / 180; this.capturedDirection = [Math.cos(a), Math.sin(a)] }
      else this.capturedDirection = normalize(dir)
      if (third.isSet) {
        const length = third.getValue()
        if (length < CONFUSION && third.hasFinishedEditing) { c.unsetOnViewParameter(third); this.capturedDirection = [0, 0]; return [x, y] }
        ;[x, y] = add(this.startPoint, mul(this.capturedDirection, length))
      } else if (fourth.isSet) [x, y] = add(this.startPoint, project(sub([x, y], this.startPoint), this.capturedDirection))
    } else if (this.state === 2) {
      const fifth = o[OVP.Fifth]
      if (fifth.isSet) {
        const radius = fifth.getValue()
        if (radius < CONFUSION && fifth.hasFinishedEditing) { c.unsetOnViewParameter(fifth); return [x, y] }
        x = this.secondPoint[0] + Math.cos(this.angle) * radius; y = this.secondPoint[1] + Math.sin(this.angle) * radius
      }
    }
    return [x, y]
  }
  adaptParameters(c: Controller, p: XY) {
    const o = c.onViewParameters
    if (this.state === 0) {
      if (!o[OVP.First].isSet) c.setOnViewParameterValue(OVP.First, p[0])
      if (!o[OVP.Second].isSet) c.setOnViewParameterValue(OVP.Second, p[1])
      const sameSign = p[0] * p[1] > 0
      o[OVP.First].setLabelAutoDistanceReverse(!sameSign); o[OVP.Second].setLabelAutoDistanceReverse(sameSign)
      o[OVP.First].setPoints([0, 0], p); o[OVP.Second].setPoints([0, 0], p)
    } else if (this.state === 1) {
      const third = o[OVP.Third], fourth = o[OVP.Fourth], vec = sub(this.secondPoint, this.startPoint)
      if (!third.isSet) c.setOnViewParameterValue(OVP.Third, len(vec))
      const range = angleOf(vec)
      if (!fourth.isSet) c.setOnViewParameterValue(OVP.Fourth, (range * 180) / Math.PI, 'Angle')
      else if (fourth.hasFinishedEditing && len(vec) > CONFUSION && Math.abs(range - (fourth.getValue() * Math.PI) / 180) > CONFUSION) c.setOnViewParameterValue(OVP.Fourth, (range * 180) / Math.PI, 'Angle')
      third.setPoints(this.startPoint, this.secondPoint)
      fourth.setPoints(this.startPoint, [0, 0])
      fourth.setLabelRange(range)
    } else if (this.state === 2) {
      const fifth = o[OVP.Fifth]
      if (!fifth.isSet) c.setOnViewParameterValue(OVP.Fifth, this.radius)
      fifth.setPoints(this.secondPoint, [this.secondPoint[0] + Math.cos(this.angle) * this.radius, this.secondPoint[1] + Math.sin(this.angle) * this.radius])
    }
  }
  computeNextDrawSketchHandlerMode(c: Controller) {
    const o = c.onViewParameters
    if (this.state === 0) { if (o[OVP.First].hasFinishedEditing && o[OVP.Second].hasFinishedEditing) this.setNextState(1) }
    else if (this.state === 1) { if (o[OVP.Third].hasFinishedEditing && o[OVP.Fourth].hasFinishedEditing) this.setNextState(2) }
    else if (this.state === 2) { if (o[OVP.Fifth].hasFinishedEditing) this.setNextState(this.states) }
  }
  /** DSHSlotController::addConstraints, with no auto-constraints diagnosed yet: the first centre's position (on the
   *  origin: a coincidence), the centres' distance, the angle unless an alignment took it, the radius. */
  addConstraints(c: Controller) {
    const o = c.onViewParameters, fc = S.highestCurveIndex() - 3
    const x0 = o[OVP.First].getValue(), y0 = o[OVP.Second].getValue()
    const x0set = o[OVP.First].isSet, y0set = o[OVP.Second].isSet
    if (x0set && y0set && x0 === 0 && y0 === 0) constraintToAttachment([fc, MID], RT_PNT_ID, x0)
    else {
      if (x0set) constraintToAttachment([fc, MID], V_AXIS_ID, x0)
      if (y0set) constraintToAttachment([fc, MID], H_AXIS_ID, y0)
    }
    if (o[OVP.Third].isSet) S.addConstraint(constraint('Distance', fc, MID, fc + 1, MID, GEO_UNDEF, NONE, f6(this.length)))
    if (o[OVP.Fourth].isSet) {
      const s1 = this.sug[1], last = s1.length ? s1[s1.length - 1].type : null
      if (last !== 'Horizontal' && last !== 'Vertical' && last !== 'Perpendicular' && last !== 'Parallel')
        S.addConstraint(constraint('Angle', H_AXIS, NONE, fc + 2, NONE, GEO_UNDEF, NONE, f6(this.angle)))
    }
    // no auto-constraint in the third state
    if (o[OVP.Fifth].isSet) S.addConstraint(constraint('Radius', fc, NONE, GEO_UNDEF, NONE, GEO_UNDEF, NONE, f6(this.radius)))
  }
}

// ── Arc slot (DrawSketchHandlerArcSlot.h) ────────────────────────────────────────────────────────────────────────
/** ArcSlotConstructionMethod: ArcSlot (arc ends: an outer and an inner arc joined by two half circles) and
 *  RectangleSlot (flat ends: two arcs joined by two radial lines). The centre, the start (the radius and the start
 *  angle), the end (the sweep), then the width. FourSeekEnd. DSHArcSlotController: the centre's X and Y, the radius and
 *  start angle, the sweep, the ends' radius (or the flat end's length); the widget's construction method. */
export class ArcSlotHandler extends DefaultHandler {
  readonly toolName = 'DSH_ArcSlot'
  protected readonly states = 4
  protected readonly methods = 2
  protected readonly autoConstraintSize = 3
  private centerPoint: XY = [0, 0]; private startPoint: XY = [0, 0]; private endPoint: XY = [0, 0]
  private startAngle = 0; private startAngleBackup = 0; private endAngle = 0; private arcAngle = 0; private r = 0; private radius = 0
  private angleReversed = false
  constructor(method = 0) { super(); this.method = method }
  crosshair() { return this.method === 0 ? 'Sketcher_Pointer_Create_ArcSlot' : 'Sketcher_Pointer_Create_RectangleSlot' }
  hints() {
    if (this.state > 3) return []
    return [this.hint(['%1 pick slot center', '%1 pick slot radius', '%1 pick slot angle', '%1 pick slot width'][this.state], [LMB]), this.hint('%1 switch mode', ['M'])]
  }
  protected update(p: XY) {
    if (this.state === 0) {
      this.ctl.drawPositionAtCursor(p)
      this.centerPoint = p
      this.seekAndRender(this.sug[0], p, [0, 0])
    } else if (this.state === 1) {
      this.ctl.drawDirectionAtCursor(p, this.centerPoint)
      this.startPoint = p
      this.startAngle = angleOf(sub(this.startPoint, this.centerPoint))
      this.startAngleBackup = this.startAngle
      this.radius = len(sub(this.startPoint, this.centerPoint))
      this.drawShape()
      this.seekAndRender(this.sug[1], p, [0, 0])
    } else if (this.state === 2) {
      this.endPoint = add(this.centerPoint, mul(normalize(sub(p, this.centerPoint)), this.radius))
      this.r = this.method === 0 ? this.radius / 10 : this.radius * 1.2
      this.startAngle = this.startAngleBackup
      const a1 = angleOf(sub(p, this.centerPoint)) - this.startAngle, a2 = a1 + (a1 < 0 ? 2 : -2) * Math.PI
      this.arcAngle = Math.abs(a1 - this.arcAngle) < Math.abs(a2 - this.arcAngle) ? a1 : a2
      this.reverseIfNecessary()
      this.drawShape()
      this.ctl.drawDoubleAtCursor(p, this.arcAngle, 'Angle')
      this.seekAndRender(this.sug[2], p, [0, 0])
    } else if (this.state === 3) {
      if (this.method === 0) this.r = Math.min(this.radius, Math.abs(this.radius - len(sub(p, this.centerPoint))))
      else this.r = len(sub(p, this.centerPoint))
      this.ctl.drawDoubleAtCursor(p, this.r)
      this.drawShape()
    }
  }
  private reverseIfNecessary() {
    if (this.arcAngle > 0) { this.endAngle = this.startAngle + this.arcAngle; this.angleReversed = false }
    else { this.endAngle = this.startAngle; this.startAngle = this.startAngle + this.arcAngle; this.angleReversed = true }
  }
  protected createShape(onlyOutline: boolean) {
    this.shapeGeometry = []; this.shapeConstraints = []
    if (this.radius < CONFUSION) return
    const pi = Math.PI, s = this.startAngle, e = this.endAngle, rev = this.angleReversed
    if (this.state === 1) this.shapeGeometry.push(this.circle(this.centerPoint, this.radius))
    else {
      if (Math.abs(this.arcAngle) < CONFUSION) return
      if (this.state === 3 && this.r < CONFUSION) return
      if (this.method === 0) {
        this.shapeGeometry.push(
          this.arc(this.centerPoint, s, e, this.radius + this.r),
          this.arc(this.startPoint, rev ? e : s + pi, rev ? e + pi : s + 2 * pi, this.r),
          this.arc(this.endPoint, rev ? s + pi : e, rev ? s + 2 * pi : pi + e, this.r))
        if (this.radius - this.r > CONFUSION) this.shapeGeometry.push(this.arc(this.centerPoint, s, e, this.radius - this.r))
      } else {
        const arc1 = this.arc(this.centerPoint, s, e, this.radius)
        const p11 = SK.getPoint([arc1], 0, START)!, p12 = SK.getPoint([arc1], 0, END)!
        this.shapeGeometry.push(arc1)
        if (this.r > CONFUSION) {
          const arc2 = this.arc(this.centerPoint, s, e, this.r)
          this.shapeGeometry.push(this.line(p11, SK.getPoint([arc2], 0, START)!), this.line(p12, SK.getPoint([arc2], 0, END)!))
          this.shapeGeometry.push(arc2) // last, so that it is easy to leave out
        } else this.shapeGeometry.push(this.line(p11, this.centerPoint), this.line(p12, this.centerPoint))
      }
    }
    if (onlyOutline) return
    const fc = S.highestCurveIndex() + 1
    if (this.method === 0) {
      const allArcs = Math.abs(this.radius - this.r) > CONFUSION
      const pos1: PointPos = rev ? START : END, pos2: PointPos = rev ? END : START
      if (allArcs) {
        this.shapeCon('Coincident', fc, MID, fc + 3, MID)
        this.shapeCon('Tangent', fc + 3, pos1, fc + 2, pos1)
        this.shapeCon('Tangent', fc + 3, pos2, fc + 1, pos2)
      } else {
        this.shapeCon('Coincident', fc, MID, fc + 1, pos2)
        this.shapeCon('Coincident', fc, MID, fc + 2, pos1)
      }
      this.shapeCon('Tangent', fc, pos1, fc + 2, pos2)
      this.shapeCon('Tangent', fc, pos2, fc + 1, pos1)
    } else {
      this.shapeCon('Perpendicular', fc, NONE, fc + 1)
      this.shapeCon('Perpendicular', fc, NONE, fc + 2)
      this.shapeCon('Coincident', fc, START, fc + 1, START)
      this.shapeCon('Coincident', fc, END, fc + 2, START)
      if (this.r > CONFUSION) {
        this.shapeCon('Coincident', fc, MID, fc + 3, MID)
        this.shapeCon('Coincident', fc + 3, START, fc + 1, END)
        this.shapeCon('Coincident', fc + 3, END, fc + 2, END)
      } else {
        this.shapeCon('Coincident', fc, MID, fc + 1, END)
        this.shapeCon('Coincident', fc, MID, fc + 2, END)
      }
    }
  }
  protected canGoToNextMode() {
    if (this.state === 1 && this.radius < CONFUSION) return false
    if (this.state === 2 && Math.abs(this.arcAngle) < CONFUSION) return false
    if (this.state === 3) return this.method === 0 ? this.r >= CONFUSION : Math.abs(this.radius - this.r) >= CONFUSION
    return true
  }
  protected angleSnappingControl() { if (this.state === 1 || this.state === 2) S.setAngleSnapping(true, this.centerPoint); else S.setAngleSnapping(false) }
  protected executeCommands() { this.createShape(false); S.openCommand('Add sketch arc slot'); this.addShape(); S.commitCommand() }
  protected generateAutoConstraints() {
    const h = S.highestCurveIndex(), [ac1, ac2, ac3] = this.sug
    this.onElement(ac1, h - 3, MID) // the centre
    if (this.method === 0) { this.onElement(ac2, h - 2, MID); this.onElement(ac3, h - 1, MID) }
    else { this.onElement(ac2, h - 3, this.arcAngle > 0 ? START : END); this.onElement(ac3, h - 3, this.arcAngle > 0 ? END : START) }
    this.removeRedundantAutoConstraints()
  }
  isWidgetVisible() { return true }
  toolWidgetText() { return 'Arc Slot Parameters' }
  toolIcon() { return 'Sketcher_CreateArcSlot' }
  ovpSpec(): OvpSpec { return { ovps: 6, widget: { parameters: 0, checkboxes: 0, comboboxes: 1, lineEdits: 0 }, firstComboIsMethod: true } }
  ovpState(i: number) { return i < 2 ? 0 : i < 4 ? 1 : i === 4 ? 2 : 3 }
  configureToolWidget(c: Controller) {
    if (!c.init) {
      c.setComboboxElements(0, ['Arc ends', 'Flat ends'])
      const k = this.isConstructionMode() ? '_Constr' : ''
      c.setComboboxItemIcon(0, 0, `Sketcher_CreateArcSlot${k}`); c.setComboboxItemIcon(0, 1, `Sketcher_CreateRectangleSlot${k}`)
    }
    const o = c.onViewParameters
    o[OVP.First].setLabelType('DISTANCEX'); o[OVP.Second].setLabelType('DISTANCEY')
    o[OVP.Third].setLabelType('RADIUS', 'Dimensioning'); o[OVP.Fourth].setLabelType('ANGLE', 'Dimensioning'); o[OVP.Fifth].setLabelType('ANGLE', 'Dimensioning')
    o[OVP.Sixth].setLabelType(this.method === 0 ? 'RADIUS' : 'DISTANCE', 'Dimensioning')
  }
  doEnforceControlParameters(c: Controller, p: XY): XY {
    const o = c.onViewParameters
    let [x, y] = p
    if (this.state === 0) {
      if (o[OVP.First].isSet) x = o[OVP.First].getValue()
      if (o[OVP.Second].isSet) y = o[OVP.Second].getValue()
    } else if (this.state === 1) {
      const third = o[OVP.Third], fourth = o[OVP.Fourth]
      let dir = sub([x, y], this.centerPoint)
      if (len(dir) < CONFUSION) dir = [1, dir[1]] // a null direction defaults to (1, 0)
      let radius = len(dir)
      if (third.isSet) {
        radius = third.getValue()
        if (radius < CONFUSION && third.hasFinishedEditing) { c.unsetOnViewParameter(third); return [x, y] }
        ;[x, y] = add(this.centerPoint, mul(normalize(dir), radius))
      }
      if (fourth.isSet) { const a = (fourth.getValue() * Math.PI) / 180; x = this.centerPoint[0] + Math.cos(a) * radius; y = this.centerPoint[1] + Math.sin(a) * radius }
    } else if (this.state === 2) {
      const fifth = o[OVP.Fifth]
      if (fifth.isSet) {
        const arcAngle = (fifth.getValue() * Math.PI) / 180
        if (Math.abs(arcAngle) % (2 * Math.PI) < CONFUSION && fifth.hasFinishedEditing) c.unsetOnViewParameter(fifth)
        else {
          this.arcAngle = arcAngle
          const length = len(sub([x, y], this.centerPoint)), a = this.startAngleBackup + arcAngle
          x = this.centerPoint[0] + Math.cos(a) * length; y = this.centerPoint[1] + Math.sin(a) * length
        }
      }
    } else if (this.state === 3) {
      const sixth = o[OVP.Sixth]
      if (sixth.isSet) {
        const radius2 = sixth.getValue()
        if (((Math.abs(radius2) < CONFUSION && this.method === 0) || (Math.abs(this.radius - radius2) < CONFUSION && this.method === 1)) && sixth.hasFinishedEditing) c.unsetOnViewParameter(sixth)
        else [x, y] = add(this.centerPoint, [this.radius + radius2, 0])
      }
    }
    return [x, y]
  }
  adaptParameters(c: Controller, p: XY) {
    const o = c.onViewParameters
    if (this.state === 0) {
      if (!o[OVP.First].isSet) c.setOnViewParameterValue(OVP.First, p[0])
      if (!o[OVP.Second].isSet) c.setOnViewParameterValue(OVP.Second, p[1])
      const sameSign = p[0] * p[1] > 0
      o[OVP.First].setLabelAutoDistanceReverse(!sameSign); o[OVP.Second].setLabelAutoDistanceReverse(sameSign)
      o[OVP.First].setPoints([0, 0], p); o[OVP.Second].setPoints([0, 0], p)
    } else if (this.state === 1) {
      if (!o[OVP.Third].isSet) c.setOnViewParameterValue(OVP.Third, this.radius)
      if (!o[OVP.Fourth].isSet) c.setOnViewParameterValue(OVP.Fourth, (this.startAngle * 180) / Math.PI, 'Angle')
      o[OVP.Third].setPoints(this.centerPoint, p)
      o[OVP.Fourth].setPoints(this.centerPoint, [0, 0])
      o[OVP.Fourth].setLabelRange(this.startAngle)
    } else if (this.state === 2) {
      if (!o[OVP.Fifth].isSet) c.setOnViewParameterValue(OVP.Fifth, (this.arcAngle * 180) / Math.PI, 'Angle')
      o[OVP.Fifth].setPoints(this.centerPoint, [0, 0])
      o[OVP.Fifth].setLabelStartAngle(this.startAngleBackup)
      o[OVP.Fifth].setLabelRange(this.arcAngle)
    } else if (this.state === 3) {
      const dist = this.method === 1 ? this.r - this.radius : this.r
      if (!o[OVP.Sixth].isSet) c.setOnViewParameterValue(OVP.Sixth, dist)
      o[OVP.Sixth].setPoints(this.endPoint, add(this.endPoint, mul(normalize(sub(this.endPoint, this.centerPoint)), dist)))
    }
  }
  computeNextDrawSketchHandlerMode(c: Controller) {
    const o = c.onViewParameters
    if (this.state === 0) { if (o[OVP.First].hasFinishedEditing && o[OVP.Second].hasFinishedEditing) this.setNextState(1) }
    else if (this.state === 1) { if (o[OVP.Third].hasFinishedEditing && o[OVP.Fourth].hasFinishedEditing) this.setNextState(2) }
    else if (this.state === 2) { if (o[OVP.Fifth].hasFinishedEditing) this.setNextState(3) }
    else if (this.state === 3) { if (o[OVP.Sixth].hasFinishedEditing) this.setNextState(this.states) }
  }
  /** DSHArcSlotController::addConstraints, with no auto-constraints diagnosed yet: the centre's position (on the origin:
   *  a coincidence), the radius (arc ends: the distance from the centre to an end's centre), the sweep, the ends'
   *  radius (flat ends: an end's length). */
  addConstraints(c: Controller) {
    const o = c.onViewParameters, fc = S.highestCurveIndex() - 3
    const x0 = o[OVP.First].getValue(), y0 = o[OVP.Second].getValue(), radius = o[OVP.Third].getValue(), slotRadius = o[OVP.Sixth].getValue()
    const x0set = o[OVP.First].isSet, y0set = o[OVP.Second].isSet
    if (x0set && y0set && x0 === 0 && y0 === 0) constraintToAttachment([fc, MID], RT_PNT_ID, 0)
    else {
      if (x0set) constraintToAttachment([fc, MID], V_AXIS_ID, x0)
      if (y0set) constraintToAttachment([fc, MID], H_AXIS_ID, y0)
    }
    if (o[OVP.Third].isSet) {
      if (this.method === 0) S.addConstraint(constraint('Distance', fc, MID, fc + 2, MID, GEO_UNDEF, NONE, f6(Math.abs(radius))))
      else S.addConstraint(constraint('Radius', fc, NONE, GEO_UNDEF, NONE, GEO_UNDEF, NONE, f6(Math.abs(radius))))
    }
    if (o[OVP.Fifth].isSet) S.addConstraint(constraint('Angle', fc, NONE, GEO_UNDEF, NONE, GEO_UNDEF, NONE, f6(Math.abs(this.arcAngle))))
    if (o[OVP.Sixth].isSet) {
      if (this.method === 0) S.addConstraint(constraint('Radius', fc + 2, NONE, GEO_UNDEF, NONE, GEO_UNDEF, NONE, f6(Math.abs(slotRadius))))
      else S.addConstraint(constraint('Distance', fc + 2, NONE, GEO_UNDEF, NONE, GEO_UNDEF, NONE, f6(Math.abs(slotRadius))))
    }
  }
}

// ── Regular polygon (DrawSketchHandlerPolygon.h) ─────────────────────────────────────────────────────────────
/** The centre, then a corner (the size and the rotation); U and J add and take away a side. TwoSeekEnd.
 *  DSHPolygonController: the centre's X and Y, the circumradius and the corner's angle; the widget's number of sides. */
export class PolygonHandler extends DefaultHandler {
  readonly toolName = 'DSH_Polygon'
  protected readonly states = 2
  protected readonly autoConstraintSize = 2
  private centerPoint: XY = [0, 0]; private firstCorner: XY = [0, 0]; private radius = 0
  constructor(private corners = 6) { super() }
  crosshair() { return 'Sketcher_Pointer_Regular_Polygon' }
  hints() {
    const sides = this.hint('%1/%2 increase/decrease number of sides', ['U', 'J'])
    return this.state === 0 ? [this.hint('%1 pick polygon center', [LMB]), sides]
      : this.state === 1 ? [this.hint('%1 pick rotation and size', [MOUSE_MOVE]), this.hint('%1 confirm', [LMB]), sides] : []
  }
  protected update(p: XY) {
    if (this.state === 0) { this.ctl.drawPositionAtCursor(p); this.centerPoint = p; this.seekAndRender(this.sug[0], p, [0, 0]) }
    else if (this.state === 1) { this.ctl.drawDirectionAtCursor(p, this.centerPoint); this.firstCorner = p; this.drawShape(); this.seekAndRender(this.sug[1], p, [0, 0]) }
  }
  protected createShape() {
    this.shapeGeometry = []
    const dv = sub(this.firstCorner, this.centerPoint)
    this.radius = len(dv)
    if (this.radius < CONFUSION) return
    const a = (2 * Math.PI) / this.corners, cos = Math.cos(a), sin = Math.sin(a)
    let [rx, ry] = dv, prev = this.firstCorner
    for (let i = 1; i <= this.corners; i++) {
      const old = rx
      rx = cos * rx - sin * ry; ry = cos * ry + sin * old
      const next: XY = [this.centerPoint[0] + rx, this.centerPoint[1] + ry]
      this.shapeGeometry.push(this.line(prev, next))
      prev = next
    }
  }
  protected canGoToNextMode() { return !(this.state === 1 && this.radius < CONFUSION) }
  protected angleSnappingControl() { if (this.state === 1) S.setAngleSnapping(true, this.centerPoint); else S.setAngleSnapping(false) }
  /** ProfileLib.RegularPolygon.makeRegularPolygon(sketch, sides, centre, corner, construction): the sides, a
   *  construction circle through the corners, the corners coincident and on the circle, the sides equal. */
  protected executeCommands() {
    S.openCommand('Add polygon')
    const n = this.corners, c: XY = [f6(this.centerPoint[0]), f6(this.centerPoint[1])], k: XY = [f6(this.firstCorner[0]), f6(this.firstCorner[1])]
    const dv = sub(k, c), step = (2 * Math.PI) / n, construction = this.isConstructionMode()
    const pts = Array.from({ length: n }, (_, i): XY => {
      const cv = Math.cos(step * i), sv = Math.sin(step * i)
      return add(c, [cv * dv[0] - sv * dv[1], cv * dv[1] + sv * dv[0]])
    })
    const first = S.addGeometry(pts.map((p, i) => this.line(p, pts[(i + 1) % n], construction))) - n + 1
    S.addGeometry(this.circle(c, len(dv), true))
    const circle = first + n, cons: Constraint[] = []
    for (let i = 0; i < n; i++) cons.push(constraint('Coincident', first + i, END, first + ((i + 1) % n), START))
    for (let i = 1; i < n; i++) cons.push(constraint('Equal', first, NONE, first + i))
    for (let i = 0; i < n; i++) cons.push(constraint('PointOnObject', first + i, END, circle))
    S.addConstraint(cons)
    S.commitCommand()
  }
  protected generateAutoConstraints() {
    // on the polygon's circle (its centre) and the last side's end
    const geo = S.getGeometry()
    for (let g = geo.length - 1; g >= 0; g--) {
      if (geo[g].type !== 'Circle') continue
      this.onElement(this.sug[0], g, MID)
      this.onElement(this.sug[1], g - 1, END)
      this.removeRedundantAutoConstraints()
      return
    }
  }
  isWidgetVisible() { return true }
  toolWidgetText() { return 'Polygon Parameters' }
  toolIcon() { return 'Sketcher_CreateRegularPolygon' }
  ovpSpec(): OvpSpec { return { ovps: 4, widget: { parameters: 1, checkboxes: 0, comboboxes: 0, lineEdits: 0 }, firstComboIsMethod: false } }
  ovpState(i: number) { return i < 2 ? 0 : 1 }
  firstKeyShortcut(c: Controller) { c.setParameterWithoutPassingFocus(0, c.getParameter(0) + 1); return true }
  secondKeyShortcut(c: Controller) { const v = c.getParameter(0); if (v > 3) c.setParameterWithoutPassingFocus(0, v - 1); return true }
  configureToolWidget(c: Controller) {
    c.setParameterLabel(0, 'Sides')
    c.setParameter(0, this.corners) // unconditionally
    c.configureParameterUnit(0, 'None')
    c.configureParameterMin(0, 3)
    c.configureParameterMax(0, 9999) // a reasonable maximum, so that the box is not very wide
    c.configureParameterDecimals(0, 0)
    const o = c.onViewParameters
    o[OVP.First].setLabelType('DISTANCEX'); o[OVP.Second].setLabelType('DISTANCEY')
    o[OVP.Third].setLabelType('DISTANCE', 'Dimensioning'); o[OVP.Fourth].setLabelType('ANGLE', 'Dimensioning')
  }
  adaptDrawingToParameterChange(_c: Controller, i: number, v: number) { if (i === 0) this.corners = Math.max(3, Math.trunc(v)) }
  doEnforceControlParameters(c: Controller, p: XY): XY {
    const o = c.onViewParameters
    let [x, y] = p
    if (this.state === 0) {
      if (o[OVP.First].isSet) x = o[OVP.First].getValue()
      if (o[OVP.Second].isSet) y = o[OVP.Second].getValue()
    } else if (this.state === 1) {
      const third = o[OVP.Third], fourth = o[OVP.Fourth]
      let dir = sub([x, y], this.centerPoint)
      if (len(dir) < CONFUSION) dir = [1, dir[1]] // a null direction defaults to (1, 0)
      let length = len(dir)
      if (third.isSet) {
        length = third.getValue()
        if (length < CONFUSION && third.hasFinishedEditing) { c.unsetOnViewParameter(third); return [x, y] }
        ;[x, y] = add(this.centerPoint, mul(normalize(dir), length))
      }
      if (fourth.isSet) { const a = (fourth.getValue() * Math.PI) / 180; x = this.centerPoint[0] + Math.cos(a) * length; y = this.centerPoint[1] + Math.sin(a) * length }
    }
    return [x, y]
  }
  adaptParameters(c: Controller, p: XY) {
    const o = c.onViewParameters
    if (this.state === 0) {
      if (!o[OVP.First].isSet) c.setOnViewParameterValue(OVP.First, p[0])
      if (!o[OVP.Second].isSet) c.setOnViewParameterValue(OVP.Second, p[1])
      const sameSign = p[0] * p[1] > 0
      o[OVP.First].setLabelAutoDistanceReverse(!sameSign); o[OVP.Second].setLabelAutoDistanceReverse(sameSign)
      o[OVP.First].setPoints([0, 0], p); o[OVP.Second].setPoints([0, 0], p)
    } else if (this.state === 1) {
      const vec = sub(this.firstCorner, this.centerPoint), range = angleOf(vec)
      if (!o[OVP.Third].isSet) c.setOnViewParameterValue(OVP.Third, len(vec))
      if (!o[OVP.Fourth].isSet) c.setOnViewParameterValue(OVP.Fourth, (range * 180) / Math.PI, 'Angle')
      o[OVP.Third].setPoints(this.centerPoint, this.firstCorner)
      o[OVP.Fourth].setPoints(this.centerPoint, [0, 0])
      o[OVP.Fourth].setLabelRange(range)
    }
  }
  computeNextDrawSketchHandlerMode(c: Controller) {
    const o = c.onViewParameters
    if (this.state === 0) { if (o[OVP.First].hasFinishedEditing && o[OVP.Second].hasFinishedEditing) this.setNextState(1) }
    else if (this.state === 1) { if (o[OVP.Third].hasFinishedEditing && o[OVP.Fourth].hasFinishedEditing) this.setNextState(this.states) }
  }
  /** DSHPolygonController::addConstraints, with no auto-constraints diagnosed yet: the centre's position, the radius,
   *  and the corner's angle (Horizontal or Vertical through the centre and the last corner, or a construction line from
   *  the centre to it at the angle). */
  addConstraints(c: Controller) {
    const o = c.onViewParameters, lastCurve = S.highestCurveIndex(), pi = Math.PI
    const x0 = o[OVP.First].getValue(), y0 = o[OVP.Second].getValue(), radius = o[OVP.Third].getValue(), angle = (o[OVP.Fourth].getValue() * pi) / 180
    if (o[OVP.First].isSet) constraintToAttachment([lastCurve, MID], V_AXIS_ID, x0)
    if (o[OVP.Second].isSet) constraintToAttachment([lastCurve, MID], H_AXIS_ID, y0)
    if (o[OVP.Third].isSet) S.addConstraint(constraint('Radius', lastCurve, NONE, GEO_UNDEF, NONE, GEO_UNDEF, NONE, f6(radius)))
    if (o[OVP.Fourth].isSet) {
      const circleGeoId = lastCurve, lastSideGeoId = lastCurve - 1
      const remainder = (a: number, b: number) => a - Math.round(a / b) * b
      if (Math.abs(remainder(angle, pi)) < CONFUSION) S.addConstraint(constraint('Horizontal', circleGeoId, MID, lastSideGeoId, END))
      else if (Math.abs(remainder(angle, pi / 2)) < CONFUSION) S.addConstraint(constraint('Vertical', circleGeoId, MID, lastSideGeoId, END))
      else {
        S.addGeometry(this.line([f6(this.centerPoint[0]), f6(this.centerPoint[1])], [f6(this.firstCorner[0]), f6(this.firstCorner[1])], true))
        const radialGeoId = S.highestCurveIndex()
        S.addConstraint(constraint('Coincident', radialGeoId, START, circleGeoId, MID))
        S.addConstraint(constraint('Coincident', radialGeoId, END, lastSideGeoId, END))
        S.addConstraint(constraint('Angle', radialGeoId, NONE, GEO_UNDEF, NONE, GEO_UNDEF, NONE, f6(angle)))
      }
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
