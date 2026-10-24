// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Sketcher/App/SketchObjectOperations.cpp: 2008 Jürgen Riegel
//   src/Mod/Sketcher/App/SketchObjectConstraints.cpp: 2008 Jürgen Riegel
//   src/Mod/Sketcher/App/SketchObjectGeometry.cpp: 2008 Jürgen Riegel
//   src/Mod/Sketcher/App/Constraint.cpp: 2008 Jürgen Riegel
//   src/Mod/Part/App/Part2DObject.cpp: 2008 Jürgen Riegel
//   src/Mod/Part/App/Geometry.cpp: 2008 Werner Mayer
// SketchObject's editing operations on a sketch's geometry and constraints, as the Sketcher's Trim, Split, Extend and
// Fillet tools call them (sketch.trim(GeoId, point), split, extend(GeoId, increment, endpoint), fillet(...)): which
// pieces the curve leaves, which constraints the pieces inherit (transferConstraints, deriveConstraintsForPieces) and
// which new ones tie them to the cutting curves. Curves are cut where they cross (Geom2dAPI_InterCurveCurve: exact for
// lines and circles, Newton's method on a sampling for the conics). The fillet is FreeCAD's between two lines; its
// moves (moveGeometry with updateGeoBeforeMoving) go to the solver through `move`.
import type { Geo, XY } from './solver'
import { type Constraint, type PointPos, NONE, START, END, MID, GEO_UNDEF, H_AXIS, V_AXIS, constraint, getPoint, coincidentPoints } from './sketch'
import * as CV from './sketchcurves'

export type Doc = { geometry: Geo[]; constraints: Constraint[] }
/** SketchObject::moveGeometry(geoId, pos, to, relative=false, updateGeoBeforeMoving=true): the geometry after the
 *  solver moved the point there, or null when the solver failed (the geometry then stays). */
export type Mover = (doc: Doc, geoId: number, pos: PointPos, to: XY) => Geo[] | null

const CONFUSION = 1e-7, PAPPROXIMATION = 1e-8
const TWO_PI = 2 * Math.PI
const sub = (a: XY, b: XY): XY => [a[0] - b[0], a[1] - b[1]], add = (a: XY, b: XY): XY => [a[0] + b[0], a[1] + b[1]]
const mul = (a: XY, k: number): XY => [a[0] * k, a[1] * k], len = (a: XY) => Math.hypot(a[0], a[1])
const dot = (a: XY, b: XY) => a[0] * b[0] + a[1] * b[1], cross = (a: XY, b: XY) => a[0] * b[1] - a[1] * b[0]
const dist = (a: XY, b: XY) => len(sub(a, b))
const normalize = (a: XY): XY => { const l = len(a); return l ? [a[0] / l, a[1] / l] : a }
/** Base::Vector3d::ProjectToLine(p, d): the perpendicular from the line through the origin along d to p, negated
 *  (FreeCAD's ProjectToLine gives the vector from p to its foot). */
const projectToLine = (p: XY, d: XY): XY => { const t = dot(p, d) / dot(d, d); return sub(mul(d, t), p) }
const clone = (c: Constraint): Constraint => ({ ...c })

// ── constraints' elements (Constraint.cpp, with the legacy First/Second/Third) ──────────────────────────────────
const elements = (c: Constraint): [number, PointPos][] => [[c.first, c.firstPos], [c.second, c.secondPos], [c.third, c.thirdPos]]
export const involvesGeoId = (c: Constraint, g: number) => c.first === g || c.second === g || c.third === g
export const involvesGeoIdAndPosId = (c: Constraint, g: number, p: PointPos) => elements(c).some(([eg, ep]) => eg === g && ep === p)
function substituteIndex(c: Constraint, from: number, to: number) {
  if (c.first === from) c.first = to
  if (c.second === from) c.second = to
  if (c.third === from) c.third = to
}
function substituteIndexAndPos(c: Constraint, fg: number, fp: PointPos, tg: number, tp: PointPos) {
  if (c.first === fg && c.firstPos === fp) { c.first = tg; c.firstPos = tp }
  if (c.second === fg && c.secondPos === fp) { c.second = tg; c.secondPos = tp }
  if (c.third === fg && c.thirdPos === fp) { c.third = tg; c.thirdPos = tp }
}
/** SketchObject::getConstraintIndices. */
const constraintIndices = (d: Doc, g: number) => d.constraints.map((c, i) => (involvesGeoId(c, g) ? i : -1)).filter((i) => i >= 0)

// ── the curves as OpenCascade parameterises them ─────────────────────────────────────────────────────────────────
const isClosedCurve = (g: Geo) => g.type === 'Circle' || g.type === 'Ellipse' || (g.type === 'BSplineCurve' && g.periodic)
function range(g: Geo): [number, number] { return CV.parameterised(g)!.range }
const valueAt = (g: Geo, u: number) => CV.parameterised(g)!.at(u)
/** ElCLib::AdjustPeriodic with Geom_TrimmedCurve::SetTrim's precision: a periodic trim in [0, 2π). */
function setTrimPeriodic(u1: number, u2: number): [number, number] {
  const preci = Math.min(Math.abs(u2 - u1) / 2, CONFUSION * 0.01)
  u1 -= Math.floor(u1 / TWO_PI) * TWO_PI
  if (TWO_PI - u1 < preci) u1 -= TWO_PI
  u2 -= Math.floor((u2 - u1) / TWO_PI) * TWO_PI
  if (u2 - u1 < preci) u2 += TWO_PI
  return [u1, u2]
}
/** GeomCurve::createArc(first, last): the same curve trimmed (a circle or an ellipse becomes its arc). */
function createArc(g: Geo, u1: number, u2: number): Geo {
  const c = g.construction ? { construction: true } : {}
  switch (g.type) {
    case 'LineSegment': return { type: 'LineSegment', start: valueAt(g, u1), end: valueAt(g, u2), ...c }
    case 'Circle': case 'ArcOfCircle': { const [a, b] = setTrimPeriodic(u1, u2); return { type: 'ArcOfCircle', center: g.center, radius: g.radius, start_angle: a, end_angle: b, ...c } }
    case 'Ellipse': case 'ArcOfEllipse': {
      const [a, b] = setTrimPeriodic(u1, u2)
      return { type: 'ArcOfEllipse', center: g.center, major_radius: g.major_radius, minor_radius: g.minor_radius, x_axis: g.x_axis, start_angle: a, end_angle: b, ...c }
    }
    case 'ArcOfHyperbola': case 'ArcOfParabola': {
      const { start_point: _s, end_point: _e, ...rest } = g
      void _s; void _e
      return { ...rest, start_angle: Math.min(u1, u2), end_angle: Math.max(u1, u2) } as Geo
    }
    default: throw new Error(`${g.type} cannot be cut here yet`)
  }
}

// ── where curves cross (Geom2dAPI_InterCurveCurve) ──────────────────────────────────────────────────────────────
type Curve = { range: [number, number]; at(u: number): XY; tangent(u: number): XY; line?: { p: XY; d: XY; infinite: boolean }; circle?: { c: XY; r: number } }
function curveOf(g: Geo): Curve | null {
  const p = CV.parameterised(g)
  if (!p) return null
  const out: Curve = { ...p }
  if (g.type === 'LineSegment') out.line = { p: g.start, d: normalize(sub(g.end, g.start)), infinite: false }
  if (g.type === 'Circle' || g.type === 'ArcOfCircle') out.circle = { c: g.center, r: g.radius }
  return out
}
function infiniteLine(p: XY, d: XY): Curve { return { range: [-1e100, 1e100], at: (u) => add(p, mul(d, u)), tangent: () => d, line: { p, d, infinite: true } } }
const inRange = (c: Curve, u: number, tol = 1e-9) => u >= c.range[0] - tol && u <= c.range[1] + tol
/** The angle of a point on a circle, brought into the curve's range when it lies there. */
function angleIn(c: Curve, q: XY): number | null {
  let a = Math.atan2(q[1] - c.circle!.c[1], q[0] - c.circle!.c[0])
  const [u0, u1] = c.range
  while (a < u0 - 1e-12) a += TWO_PI
  while (a > u0 + TWO_PI) a -= TWO_PI
  return a <= u1 + 1e-12 ? a : null
}
/** The points where two curves meet, overlaps given by their ends (IntRes2d's segments' first and last points). */
export function intersect(a: Curve, b: Curve): XY[] {
  const out: XY[] = []
  if (a.line && b.line) {
    const den = cross(a.line.d, b.line.d), qp = sub(b.line.p, a.line.p)
    if (Math.abs(den) < 1e-12) {
      if (Math.abs(cross(qp, a.line.d)) > 1e-9) return []
      // collinear: the overlap's ends
      const ta = (q: XY) => dot(sub(q, a.line!.p), a.line!.d)
      const ends: XY[] = []
      for (const u of [b.range[0], b.range[1]]) if (!b.line.infinite) { const q = b.at(u); if (inRange(a, ta(q))) ends.push(q) }
      for (const u of [a.range[0], a.range[1]]) if (!a.line.infinite) { const q = a.at(u); const tb = dot(sub(q, b.line.p), b.line.d); if (inRange(b, tb)) ends.push(q) }
      return ends
    }
    const t = cross(qp, b.line.d) / den, s = cross(qp, a.line.d) / den
    if (inRange(a, t) && inRange(b, s)) out.push(a.at(t))
    return out
  }
  if ((a.line && b.circle) || (a.circle && b.line)) {
    const [l, c] = a.line ? [a, b] : [b, a]
    const f = sub(l.line!.p, c.circle!.c), bq = dot(f, l.line!.d), disc = bq * bq - (dot(f, f) - c.circle!.r ** 2)
    if (disc < -1e-12) return []
    const ts = Math.abs(disc) <= 1e-14 ? [-bq] : [-bq - Math.sqrt(Math.max(0, disc)), -bq + Math.sqrt(Math.max(0, disc))]
    for (const t of ts) { if (!inRange(l, t)) continue; const q = l.at(t); if (angleIn(c, q) !== null) out.push(q) }
    return out
  }
  if (a.circle && b.circle) {
    const d = dist(a.circle.c, b.circle.c), r1 = a.circle.r, r2 = b.circle.r
    if (d < 1e-12) {
      if (Math.abs(r1 - r2) > 1e-12) return []
      // the same circle: the overlap's ends
      const ends: XY[] = []
      for (const [x, y] of [[a, b], [b, a]] as [Curve, Curve][]) for (const u of x.range) { const q = x.at(u); if (angleIn(y, q) !== null && Math.abs(x.range[1] - x.range[0] - TWO_PI) > 1e-12) ends.push(q) }
      return ends
    }
    if (d > r1 + r2 + 1e-12 || d < Math.abs(r1 - r2) - 1e-12) return []
    const k = (r1 * r1 - r2 * r2 + d * d) / (2 * d), h = Math.sqrt(Math.max(0, r1 * r1 - k * k))
    const ex = mul(sub(b.circle.c, a.circle.c), 1 / d), m = add(a.circle.c, mul(ex, k))
    const pts: XY[] = h < 1e-12 ? [m] : [[m[0] - h * ex[1], m[1] + h * ex[0]], [m[0] + h * ex[1], m[1] - h * ex[0]]]
    for (const q of pts) if (angleIn(a, q) !== null && angleIn(b, q) !== null) out.push(q)
    return out
  }
  return intersectNumeric(a, b)
}
/** Two curves' crossings found on polylines of them and refined by Newton's method on C1(u) = C2(v). */
function intersectNumeric(a: Curve, b: Curve): XY[] {
  const sample = (c: Curve) => {
    let [u0, u1] = c.range
    if (c.line?.infinite) { u0 = -1e4; u1 = 1e4 }
    const n = 400, us = Array.from({ length: n + 1 }, (_, i) => u0 + ((u1 - u0) * i) / n)
    return { us, pts: us.map((u) => c.at(u)) }
  }
  const A = sample(a), B = sample(b), out: XY[] = []
  for (let i = 0; i < A.pts.length - 1; i++) for (let j = 0; j < B.pts.length - 1; j++) {
    const p = A.pts[i], r = sub(A.pts[i + 1], p), q = B.pts[j], s = sub(B.pts[j + 1], q)
    const den = cross(r, s)
    if (Math.abs(den) < 1e-18) continue
    const t = cross(sub(q, p), s) / den, w = cross(sub(q, p), r) / den
    if (t < -0.05 || t > 1.05 || w < -0.05 || w > 1.05) continue
    let u = A.us[i] + t * (A.us[i + 1] - A.us[i]), v = B.us[j] + w * (B.us[j + 1] - B.us[j])
    let ok = false
    for (let it = 0; it < 60; it++) {
      const e = sub(a.at(u), b.at(v)), ta = a.tangent(u), tb = b.tangent(v)
      const det = -ta[0] * tb[1] + ta[1] * tb[0]
      if (Math.abs(det) < 1e-300) break
      const du = (-e[0] * -tb[1] + tb[0] * -e[1]) / det, dv = (ta[0] * -e[1] - -e[0] * ta[1]) / det
      u += du; v += dv
      if (Math.abs(du) + Math.abs(dv) < 1e-15 * (1 + Math.abs(u) + Math.abs(v))) { ok = true; break }
    }
    if (!ok && dist(a.at(u), b.at(v)) > 1e-10) continue
    if (!inRange(a, u) || !inRange(b, v)) continue
    const x = a.at(u)
    if (!out.some((o) => dist(o, x) < 1e-9)) out.push(x)
  }
  return out
}

// ── SketchObject::seekTrimPoints / Part2DObject::seekTrimPoints ─────────────────────────────────────────────────
/** The two points around `point` where the curve geoId is cut, and the curves cutting it there: cuttingGeoIds[0]
 *  before the picked point, [1] after it (GEO_UNDEF where none). null when nothing cuts it. */
export function seekTrimPoints(d: Doc, geoId: number, point: XY, includeSketchAxes = false): { ids: [number, number]; points: [XY, XY] } | null {
  const g = d.geometry[geoId]
  if (!g) return null
  const primary = curveOf(g)
  if (!primary) return null
  // GeomAPI::To2d of a trimmed curve is not periodic (FreeCAD's answers say so): only full circles, ellipses and
  // periodic B-splines are
  const periodic = g.type === 'Circle' || g.type === 'Ellipse' || (g.type === 'BSplineCurve' && g.periodic)
  const period = g.type === 'BSplineCurve' ? range(g)[1] - range(g)[0] : TWO_PI
  const project = (p: XY) => { const u = CV.closestParameter(g, p)!; return { u, d: dist(primary.at(u), p) } }
  const picked = project(point).u
  let i1 = -1, i2 = -1, param1 = -1e10, param2 = 1e10
  let p1: XY = [0, 0], p2: XY = [0, 0]
  const others: { id: number; curve: Curve; bounded: Geo | null }[] = []
  d.geometry.forEach((og, id) => { if (id !== geoId) { const c = curveOf(og); if (c) others.push({ id, curve: c, bounded: og }) } })
  if (includeSketchAxes) {
    others.push({ id: d.geometry.length, curve: infiniteLine([0, 0], [1, 0]), bounded: null })
    others.push({ id: d.geometry.length + 1, curve: infiniteLine([0, 0], [0, 1]), bounded: null })
  }
  for (const o of others) {
    const pts: XY[] = []
    // #2463: the ends of a bounded secondary curve on the primary curve
    if (o.bounded && o.bounded.type !== 'Point' && o.bounded.type !== 'Circle' && o.bounded.type !== 'Ellipse') {
      pts.push(getPoint(d.geometry, o.id, START)!, getPoint(d.geometry, o.id, END)!)
    }
    pts.push(...intersect(primary, o.curve))
    for (const p of pts) {
      const pr = project(p)
      if (pr.d > CONFUSION) continue
      let param = pr.u
      if (periodic) {
        param = param - period * Math.ceil((param - picked) / period)
        if (param > param1) { param1 = param; p1 = p; i1 = o.id }
        param -= period
        if (param < param2) { param2 = param; p2 = p; i2 = o.id }
      } else if (param < picked && param > param1) { param1 = param; p1 = p; i1 = o.id }
      else if (param > picked && param < param2) { param2 = param; p2 = p; i2 = o.id }
    }
  }
  if (periodic && Math.abs(param2 - param1 - period) < 1e-10) {
    if (param2 - picked >= picked - param1) i2 = -1
    else i1 = -1
  }
  if (i1 < 0 && i2 < 0) return null
  const geoIdOf = (i: number) => (i < 0 ? GEO_UNDEF : includeSketchAxes && i === d.geometry.length ? H_AXIS : includeSketchAxes && i === d.geometry.length + 1 ? V_AXIS : i)
  return { ids: [geoIdOf(i1), geoIdOf(i2)], points: [p1, p2] }
}

// ── deleting (SketchObject::delGeometry, delGeometriesExclusiveList, delConstraintOnPoint) ──────────────────────
/** getDirectlyCoincidentPoints(GeoId, PosId): the point and those a Coincident or an endpoint Tangent ties to it, or
 *  nothing when there are none. */
export function directlyCoincident(d: Doc, g: number, pos: PointPos): [number, PointPos][] {
  const out: [number, PointPos][] = [[g, pos]]
  for (const c of d.constraints) {
    if (c.type === 'Coincident') {
      if (c.first === g && c.firstPos === pos) out.push([c.second, c.secondPos])
      else if (c.second === g && c.secondPos === pos) out.push([c.first, c.firstPos])
    }
    if (c.type === 'Tangent') {
      if (c.first === g && c.firstPos === pos && (c.secondPos === START || c.secondPos === END)) out.push([c.second, c.secondPos])
      if (c.second === g && c.secondPos === pos && (c.firstPos === START || c.firstPos === END)) out.push([c.first, c.firstPos])
    }
  }
  return out.length === 1 ? [] : out
}
/** SketchObject::transferConstraints. */
export function transferConstraints(d: Doc, fg: number, fp: PointPos, tg: number, tp: PointPos, doNotTransformTangencies = false) {
  d.constraints = d.constraints.map((c) => {
    if (c.type === 'InternalAlignment') return c
    if (!involvesGeoIdAndPosId(c, fg, fp) || involvesGeoIdAndPosId(c, tg, tp)) return c
    const n = clone(c)
    substituteIndexAndPos(n, fg, fp, tg, tp)
    if (c.first < 0 && c.second < 0) return c
    if (c.type === 'Tangent' || c.type === 'Perpendicular') { if (!doNotTransformTangencies) n.type = 'Coincident' }
    else if (c.type === 'Angle') return c
    return n
  })
}
/** SketchObject::delConstraintOnPoint(geoId, posId, onlyCoincident). */
export function delConstraintOnPoint(d: Doc, g: number, pos: PointPos, onlyCoincident: boolean) {
  const vals = d.constraints
  let rg = GEO_UNDEF, rp: PointPos = NONE
  const found = vals.find((c) => c.type === 'Coincident' && involvesGeoIdAndPosId(c, g, pos))
  if (found) { if (found.first === g && found.firstPos === pos) { rg = found.second; rp = found.secondPos } else { rg = found.first; rp = found.firstPos } }
  const transfer = (c: Constraint, which: 'first' | 'second') => {
    if (rg === GEO_UNDEF) return false
    const gk = which, pk = which === 'first' ? 'firstPos' : 'secondPos'
    if (g !== c[gk] || pos !== c[pk]) return false
    c[gk] = rg; (c as Record<string, unknown>)[pk] = rp
    return true
  }
  const out: Constraint[] = []
  for (const c0 of vals) {
    if (!involvesGeoIdAndPosId(c0, g, pos)) {
      const distance = c0.type === 'Distance' || c0.type === 'DistanceX' || c0.type === 'DistanceY'
      if (distance && c0.first === g && c0.firstPos === NONE && (pos === START || pos === END)) continue
      out.push(c0)
      continue
    }
    const c = clone(c0)
    let keep: boolean | null
    if (c.type !== 'Coincident' && onlyCoincident) keep = true
    else switch (c.type) {
      case 'Coincident':
        if (rg === GEO_UNDEF || involvesGeoIdAndPosId(c, rg, rp)) keep = false
        else { substituteIndexAndPos(c, g, pos, rg, rp); keep = true }
        break
      case 'Distance': case 'DistanceX': case 'DistanceY': keep = transfer(c, 'first') || transfer(c, 'second'); break
      case 'PointOnObject': keep = transfer(c, 'first'); break
      case 'Tangent': case 'Perpendicular': case 'Vertical': case 'Horizontal': case 'Symmetric': keep = false; break
      default: keep = null
    }
    if (keep ?? true) out.push(keep === true && c.type !== c0.type ? c : c)
  }
  d.constraints = out
}
/** SketchObject::changeConstraintAfterDeletingGeo: null when the constraint goes with the geometry. */
function afterDeletingGeo(c: Constraint, deleted: number): Constraint | null {
  if (involvesGeoId(c, deleted)) return null
  const n = clone(c)
  const fix = (g: number) => (deleted >= 0 ? (g > deleted ? g - 1 : g) : (g < deleted && g !== GEO_UNDEF ? g + 1 : g))
  n.first = fix(n.first); n.second = fix(n.second); n.third = fix(n.third)
  return n
}
/** SketchObject::delGeometriesExclusiveList. */
export function delGeometriesExclusive(d: Doc, ids: number[]) {
  const s = [...new Set(ids)].sort((a, b) => a - b)
  if (!s.length) return
  for (const g of [...s].reverse()) {
    for (const pos of [START, END, MID] as PointPos[]) {
      const list = directlyCoincident(d, g, pos)
      if (list.length > 1) { delConstraintOnPoint(d, g, pos, true); transferConstraints(d, list[0][0], list[0][1], list[1][0], list[1][1]) }
    }
  }
  let cons = d.constraints
  for (const g of [...s].reverse()) cons = cons.map((c) => afterDeletingGeo(c, g)).filter((c): c is Constraint => !!c)
  d.constraints = cons
  d.geometry = d.geometry.filter((_, i) => !s.includes(i))
}
/** SketchObject::delGeometries: internal geometry goes with its parent. */
export function delGeometries(d: Doc, ids: number[]) {
  const s = ids.filter((g) => g >= 0)
  for (const c of d.constraints) if (c.type === 'InternalAlignment' && s.includes(c.second)) s.push(c.first)
  delGeometriesExclusive(d, s)
}
const hasInternalGeometry = (g: Geo) => CV.isConic(g) || g.type === 'BSplineCurve'
/** GeomConic or GeomArcOfConic: the curves with a centre (circles and arcs of circle too). */
const hasMid = (g: Geo) => CV.isConic(g) || g.type === 'Circle' || g.type === 'ArcOfCircle'
/** SketchObject::delGeometry(GeoId, IncludeInternalGeometry): a conic or a B-spline takes its internal geometry
 *  along (deleteUnusedInternalGeometry with delgeoid). */
export function delGeometry(d: Doc, g: number, includeInternal: boolean) {
  if (includeInternal && hasInternalGeometry(d.geometry[g])) {
    const internal = d.constraints.filter((c) => c.type === 'InternalAlignment' && c.second === g).map((c) => c.first)
    for (const id of [...internal, g].sort((a, b) => b - a)) delGeometriesExclusive(d, [id])
    return
  }
  delGeometriesExclusive(d, [g])
}
/** SketchObject::delConstraints. */
function delConstraints(d: Doc, ids: number[]) { const gone = new Set(ids); d.constraints = d.constraints.filter((_, i) => !gone.has(i)) }

// ── trim (SketchObject::trim) ────────────────────────────────────────────────────────────────────────────────────
const isPointAtPosition = (d: Doc, g: number, pos: PointPos, p: XY) => { const q = getPoint(d.geometry, g, pos); return !!q && dist(p, q) < 500 * CONFUSION }
function transformPreexistingForTrim(d: Doc, c: Constraint, geoId: number, cutting: number, cut: XY, newId: number, newPos: PointPos): Constraint | null {
  if (cutting === GEO_UNDEF || !involvesGeoId(c, cutting) || !involvesGeoIdAndPosId(c, geoId, NONE)) return null
  if (c.type === 'PointOnObject') {
    if (isPointAtPosition(d, c.first, c.firstPos, cut)) return { ...clone(c), type: 'Coincident', second: newId, secondPos: newPos }
    return null
  }
  if (c.type === 'Tangent' || c.type === 'Perpendicular') {
    const n = clone(c)
    substituteIndexAndPos(n, geoId, NONE, newId, newPos)
    if (n.firstPos === NONE) { [n.first, n.second] = [n.second, n.first]; [n.firstPos, n.secondPos] = [n.secondPos, n.firstPos] }
    n.third = GEO_UNDEF; n.thirdPos = NONE
    return n
  }
  return null
}
function newConstraintAtTrimCut(d: Doc, cutting: number, cutGeo: number, cutPos: PointPos, p: XY): Constraint {
  if (isPointAtPosition(d, cutting, START, p)) return constraint('Coincident', cutGeo, cutPos, cutting, START)
  if (isPointAtPosition(d, cutting, END, p)) return constraint('Coincident', cutGeo, cutPos, cutting, END)
  return constraint('PointOnObject', cutGeo, cutPos, cutting)
}
/** findPieceContainingPoint. */
function pieceContaining(d: Doc, geo: Geo, p: XY, newGeos: Geo[]): number | null {
  let u = CV.closestParameter(geo, p)!
  for (let i = 0; i < newGeos.length; i++) {
    const [f, l] = range(newGeos[i])
    if (f - u > PAPPROXIMATION && isClosedCurve(geo)) u += range(geo)[1] - range(geo)[0]
    if (f - u <= PAPPROXIMATION && u - l <= PAPPROXIMATION) return i
  }
  return null
}
/** SketchObject::deriveConstraintsForPieces. */
function deriveConstraintsForPieces(d: Doc, oldId: number, newIds: number[], newGeos: Geo[], con: Constraint, out: Constraint[], assumeTangency: boolean): boolean {
  const geo = d.geometry[oldId]
  let [conId, conPos] = [con.first, con.firstPos]
  if (conId === oldId) [conId, conPos] = [con.second, con.secondPos]
  let toAll = false
  switch (con.type) {
    case 'Horizontal': case 'Vertical': case 'Parallel': toAll = geo.type === 'LineSegment'; break
    case 'Tangent': case 'Perpendicular': {
      if (!assumeTangency && geo.type === 'LineSegment') { toAll = true; break }
      const conGeo = d.geometry[conId]
      if (!conGeo || conGeo.type === 'Point') return false
      for (let i = 0; i < newIds.length; i++) {
        const coincident = d.constraints.some((c) => c.type === 'Coincident' && involvesGeoId(c, newIds[i]) && involvesGeoId(c, conId))
        let meets = false
        if (!coincident) { const a = curveOf(newGeos[i]), b = curveOf(conGeo); meets = !!a && !!b && intersect(a, b).length > 0 }
        if (coincident || meets) { const t = clone(con); substituteIndex(t, oldId, newIds[i]); out.push(t); return true }
      }
      break
    }
    case 'Angle': {
      const [tg, tp] = [con.third, con.thirdPos]
      if (tg === oldId) {
        const list = directlyCoincident(d, tg, tp)
        if (list.length <= 1) return false
        const idx = pieceContaining(d, geo, getPoint(d.geometry, tg, tp)!, newGeos)
        if (idx !== null) { const t = clone(con); substituteIndexAndPos(t, list[0][0], list[0][1], list[1][0], list[1][1]); substituteIndex(t, oldId, newIds[idx]); out.push(t); return true }
      } else if (tg !== GEO_UNDEF) {
        const idx = pieceContaining(d, geo, getPoint(d.geometry, tg, tp)!, newGeos)
        if (idx !== null) { const t = clone(con); substituteIndex(t, oldId, newIds[idx]); out.push(t); return true }
        break
      } else if (newGeos.some((g) => g.type !== 'LineSegment')) return false
      else { toAll = true; break }
      break
    }
    case 'Distance': case 'DistanceX': case 'DistanceY': case 'Coincident': case 'PointOnObject': {
      if (con.firstPos === NONE && con.secondPos === NONE && newIds.length > 1) {
        out.push({ ...clone(con), first: newIds[0], firstPos: START, second: newIds[newIds.length - 1], secondPos: END })
        return true
      }
      if (conId === GEO_UNDEF) return false
      const cp = getPoint(d.geometry, conId, conPos)
      if (!cp) return false
      let u = CV.closestParameter(geo, cp)!
      for (let i = 0; i < newIds.length; i++) {
        const [f, l] = range(newGeos[i])
        if (f - u > PAPPROXIMATION && isClosedCurve(geo)) u += range(geo)[1] - range(geo)[0]
        if (f - u <= PAPPROXIMATION && u - l <= PAPPROXIMATION) {
          out.push({ ...clone(con), first: conId, firstPos: conPos, second: newIds[i], secondPos: NONE })
          return true
        }
      }
      break
    }
    case 'Radius': case 'Diameter': case 'Equal':
      if (hasMid(geo)) { const t = clone(con); substituteIndex(t, oldId, newIds[0]); out.push(t) }
      break
    default: break
  }
  if (!toAll) return false
  if (assumeTangency) { const t = clone(con); substituteIndex(t, oldId, newIds[0]); out.push(t) }
  else for (const id of newIds) { const t = clone(con); substituteIndex(t, oldId, id); out.push(t) }
  return true
}
/** SketchObject::trim(GeoId, point, includeSketchAxes): true when done. */
export function trim(d: Doc, geoId: number, point: XY, includeSketchAxes = false): boolean {
  const geo = d.geometry[geoId]
  if (!geo || geo.type === 'Point' || d.constraints.some((c) => c.type === 'InternalAlignment' && c.first === geoId)) return false
  if (geo.type === 'BSplineCurve') throw new Error('Trimming a B-spline is not in this workbench yet')
  const construction = !!geo.construction, closed = isClosedCurve(geo)
  const seek = seekTrimPoints(d, geoId, point, includeSketchAxes)
  if (!seek) { delGeometry(d, geoId, true); return true }
  const cutting: [number, number] = [...seek.ids], cuts = seek.points
  // getParamLimitsOfNewGeosForTrim
  const [first, last] = range(geo)
  const c0 = CV.closestParameter(geo, cuts[0])!, c1 = CV.closestParameter(geo, cuts[1])!
  if (!closed && Math.abs(first - c0) < PAPPROXIMATION) cutting[0] = GEO_UNDEF
  if (!closed && Math.abs(last - c1) < PAPPROXIMATION) cutting[1] = GEO_UNDEF
  const undefs = cutting.filter((g) => g === GEO_UNDEF).length
  let params: [number, number][]
  if (undefs === 0 && dist(cuts[0], cuts[1]) < 500 * CONFUSION) params = []
  else {
    params = Array.from({ length: 2 - undefs }, () => [first, last] as [number, number])
    if (params.length && closed) params.pop()
    if (params.length) {
      if (cutting[0] !== GEO_UNDEF) params[0][1] = c0
      if (cutting[1] !== GEO_UNDEF) params[params.length - 1][0] = c1
    }
  }
  if (!params.length) { delGeometry(d, geoId, true); return true }
  const newIds = params.length === 1 ? [geoId] : [geoId, d.geometry.length]
  const newGeos = params.map(([a, b]) => createArc(geo, a, b))
  // the constraints to transfer by hand
  let oldIds = constraintIndices(d, geoId)
  if (!closed) {
    oldIds = oldIds.filter((i) => {
      const c = d.constraints[i]
      const s = involvesGeoIdAndPosId(c, geoId, START), e = involvesGeoIdAndPosId(c, geoId, END)
      const keepStart = cutting[0] !== GEO_UNDEF, keepEnd = cutting[1] !== GEO_UNDEF
      const both = s && e && !(keepStart && keepEnd)
      return !(!both && ((s && keepStart) || (e && keepEnd)))
    })
  }
  oldIds = oldIds.filter((i) => !involvesGeoIdAndPosId(d.constraints[i], geoId, MID))
  // createNewConstraintsForTrim
  const newCons: Constraint[] = [], toDelete = new Set<number>()
  let point1Done = false, point2Done = false
  const conic = hasMid(geo)
  for (const id of oldIds) {
    const con = d.constraints[id]
    if (con.type === 'InternalAlignment') {
      if (conic) newCons.push({ ...clone(con), second: newIds[0] })
      else toDelete.add(con.first)
      continue
    }
    let n = transformPreexistingForTrim(d, con, geoId, cutting[0], cuts[0], newIds[0], END)
    if (n) { newCons.push(n); point1Done = true; continue }
    n = transformPreexistingForTrim(d, con, geoId, cutting[1], cuts[1], newIds[newIds.length - 1], START)
    if (n) { newCons.push(n); point2Done = true; continue }
    if (!(con.type === 'Angle' || involvesGeoIdAndPosId(con, geoId, NONE))) continue
    deriveConstraintsForPieces(d, geoId, newIds, newGeos, con, newCons, false)
  }
  if (cutting[0] !== GEO_UNDEF && !point1Done) newCons.push(newConstraintAtTrimCut(d, cutting[0], newIds[0], END, cuts[0]))
  if (cutting[1] !== GEO_UNDEF && !point2Done) newCons.push(newConstraintAtTrimCut(d, cutting[1], newIds[newIds.length - 1], START, cuts[1]))
  // replace
  delConstraints(d, oldIds)
  if (!closed) {
    transferConstraints(d, geoId, START, newIds[0], START, true)
    transferConstraints(d, geoId, END, newIds[newIds.length - 1], END, true)
  }
  if (conic) {
    transferConstraints(d, geoId, MID, newIds[0], MID, true)
    if (newIds.length > 1) newCons.push(constraint('Coincident', newIds[0], MID, newIds[newIds.length - 1], MID))
  }
  d.geometry = [...d.geometry]
  d.geometry[geoId] = newGeos[0]
  for (let i = 1; i < newGeos.length; i++) d.geometry.push(newGeos[i])
  for (const id of newIds) d.geometry[id] = construction ? { ...d.geometry[id], construction: true } : withoutConstruction(d.geometry[id])
  let added = newCons
  for (const g of [...toDelete].sort((a, b) => b - a)) added = added.map((c) => afterDeletingGeo(c, g)).filter((c): c is Constraint => !!c)
  delGeometries(d, [...toDelete])
  d.constraints = [...d.constraints, ...added]
  return true
}
function withoutConstruction(g: Geo): Geo { const { construction: _c, ...rest } = g as Geo & { construction?: boolean }; void _c; return rest as Geo }

// ── split (SketchObject::split) ──────────────────────────────────────────────────────────────────────────────────
export function split(d: Doc, geoId: number, point: XY): boolean {
  const geo = d.geometry[geoId]
  if (!geo || geo.type === 'Point') return false
  if (geo.type === 'BSplineCurve') throw new Error('Splitting a B-spline is not in this workbench yet')
  const closed = isClosedCurve(geo)
  const u = CV.closestParameter(geo, point)!
  const [first, last] = range(geo)
  const params: [number, number][] = closed ? [[u, u + last - first]] : [[first, u], [u, last]]
  const newIds = params.length === 1 ? [geoId] : [geoId, d.geometry.length]
  const newGeos = params.map(([a, b]) => createArc(geo, a, b))
  let oldIds = constraintIndices(d, geoId)
  oldIds = oldIds.filter((i) => involvesGeoIdAndPosId(d.constraints[i], geoId, NONE))
  const newCons: Constraint[] = []
  if (!closed && newIds.length > 1) {
    transferConstraints(d, geoId, START, newIds[0], START, true)
    transferConstraints(d, geoId, END, newIds[newIds.length - 1], END, true)
  }
  for (const id of oldIds) deriveConstraintsForPieces(d, geoId, newIds, newGeos, d.constraints[id], newCons, true)
  let joint: Constraint | null = null
  if (!closed && newIds.length > 1) { joint = constraint('Coincident', newIds[0], END, newIds[newIds.length - 1], START); newCons.push(joint) }
  if (hasMid(geo) && newIds.length > 1) newCons.push(constraint('Coincident', newIds[0], MID, newIds[newIds.length - 1], MID))
  else if (joint && geo.type === 'LineSegment') joint.type = 'Tangent'
  if (hasMid(geo)) transferConstraints(d, geoId, MID, newIds[0], MID)
  delConstraints(d, oldIds)
  d.geometry = [...d.geometry]
  d.geometry[geoId] = newGeos[0]
  for (let i = 1; i < newGeos.length; i++) d.geometry.push(newGeos[i])
  d.constraints = [...d.constraints, ...newCons]
  return true
}

// ── extend (SketchObject::extend) ────────────────────────────────────────────────────────────────────────────────
/** SketchObject::extend(GeoId, increment, endpoint): a line's end moved along it (through the solver), an arc's
 *  range widened. */
export function extend(d: Doc, geoId: number, increment: number, endpoint: PointPos, move: Mover): boolean {
  const g = d.geometry[geoId]
  if (!g) return false
  if (g.type === 'LineSegment') {
    const [a, b] = endpoint === START ? [g.start, g.end] : [g.end, g.start]
    const v = sub(a, b), scale = len(v) + increment
    const to = add(mul(normalize(v), scale), b)
    const out = move(d, geoId, endpoint, to)
    if (!out) return false
    d.geometry = out
    return true
  }
  if (g.type === 'ArcOfCircle') {
    const [s, e] = endpoint === START ? [g.start_angle - increment, g.end_angle] : [g.start_angle, g.end_angle + increment]
    const [a, b] = setTrimPeriodic(s, e)
    d.geometry = d.geometry.map((x, i) => (i === geoId ? { ...g, start_angle: a, end_angle: b } : x))
    return true
  }
  return false
}

// ── fillet (SketchObject::fillet, Part's createFilletGeometry for two lines) ────────────────────────────────────
type Line = Extract<Geo, { type: 'LineSegment' }>
/** find2DLinesIntersection. */
function linesIntersection(o1: XY, d1: XY, o2: XY, d2: XY): XY | null {
  const det = d1[0] * d2[1] - d1[1] * d2[0]
  if (Math.abs(det) < 1e-10) return null
  const c1 = d1[1] * o1[0] - d1[0] * o1[1], c2 = d2[1] * o2[0] - d2[0] * o2[1]
  return [(d1[0] * c2 - d2[0] * c1) / det, (d1[1] * c2 - d2[1] * c1) / det]
}
const segIntersection = (l1: Line, l2: Line) => linesIntersection(l1.start, sub(l1.end, l1.start), l2.start, sub(l2.end, l2.start))
/** findFilletCenter. */
function filletCenter(l1: Line, l2: Line, radius: number, ref1: XY, ref2: XY): XY | null {
  const dir1 = normalize(sub(l1.start, l1.end)), dir2 = normalize(sub(l2.start, l2.end))
  let n1 = normalize([dir1[1], -dir1[0]]), n2 = normalize([dir2[1], -dir2[0]])
  const corner = segIntersection(l1, l2)
  if (!corner) return null
  const np1 = add(projectToLine(sub(ref1, l1.start), sub(l1.end, l1.start)), ref1)
  const np2 = add(projectToLine(sub(ref2, l2.start), sub(l2.end, l2.start)), ref2)
  const bisect = normalize(add(normalize(sub(np1, corner)), normalize(sub(np2, corner))))
  const i1 = linesIntersection(np1, n1, corner, bisect), i2 = linesIntersection(np2, n2, corner, bisect)
  if (!i1 || !i2) return null
  n1 = normalize(sub(i1, np1)); n2 = normalize(sub(i2, np2))
  return linesIntersection(add(l1.start, mul(n1, radius)), dir1, add(l2.start, mul(n2, radius)), dir2)
}
/** create2LinesFilletGeometry. */
function lineFilletArc(l1: Line, l2: Line, center: XY, radius: number): Extract<Geo, { type: 'ArcOfCircle' }> | null {
  const corner = segIntersection(l1, l2)
  if (!corner) return null
  const d1 = sub(l1.end, l1.start), d2 = sub(l2.end, l2.start)
  const r1 = mul(projectToLine(sub(center, corner), d1), 1), r2 = projectToLine(sub(center, corner), d2)
  let start = Math.atan2(r1[1], r1[0])
  const span = Math.atan2(-r1[1] * r2[0] + r1[0] * r2[1], r1[0] * r2[0] + r1[1] * r2[1])
  let end = start + span
  if (end < start) [start, end] = [end, start]
  if (end > TWO_PI) end -= TWO_PI
  if (start < 0) end += TWO_PI
  const [a, b] = setTrimPeriodic(start, end)
  return { type: 'ArcOfCircle', center, radius, start_angle: a, end_angle: b }
}
/** suggestFilletRadius: the radius the fillet tool picks for two lines and where they were picked, or -1. */
export function suggestFilletRadius(l1: Line, l2: Line, ref1: XY, ref2: XY): number {
  const corner = segIntersection(l1, l2)
  if (!corner) return -1
  let d1 = sub(l1.end, l1.start), d2 = sub(l2.end, l2.start)
  if (dot(d1, sub(ref1, corner)) < 0) d1 = mul(d1, -1)
  if (dot(d2, sub(ref2, corner)) < 0) d2 = mul(d2, -1)
  const bis = normalize(add(normalize(d1), normalize(d2)))
  const p1 = add(projectToLine(sub(ref1, corner), d1), ref1), p2 = add(projectToLine(sub(ref2, corner), d2), ref2)
  const n1: XY = [d1[1], -d1[0]], n2: XY = [d2[1], -d2[0]]
  let r1 = -1, r2 = -1
  const c1 = linesIntersection(p1, n1, corner, bis), c2 = linesIntersection(p2, n2, corner, bis)
  if (c1) r1 = dist(p1, c1)
  if (c2) r2 = dist(p1, c2)
  return r1 < r2 ? r1 : r2
}
/** chooseFilletsEdges. */
function chooseFilletEdges(d: Doc, list: [number, PointPos][]): [number, PointPos][] {
  if (list.length === 2) return list
  const out: [number, PointPos][] = []
  for (const e of list) { if (!d.geometry[e[0]]?.construction) { out.push(e); if (out.length > 2) return [] } }
  return out
}
/** The radius the fillet tool picks at a corner (DrawSketchHandlerFillet: 0.2 × the shorter line × sin(angle / 2)),
 *  or -1 when the corner is not two lines. */
export function cornerFilletRadius(d: Doc, g: number, pos: PointPos): number {
  const list = chooseFilletEdges(d, directlyCoincident(d, g, pos))
  if (list.length !== 2 || list[0][0] < 0 || list[1][0] < 0) return -1
  const a = d.geometry[list[0][0]], b = d.geometry[list[1][0]]
  if (a.type !== 'LineSegment' || b.type !== 'LineSegment') return -1
  let d1 = sub(a.end, a.start), d2 = sub(b.end, b.start)
  if (list[0][1] === END) d1 = mul(d1, -1)
  if (list[1][1] === END) d2 = mul(d2, -1)
  const angle = Math.acos(Math.max(-1, Math.min(1, dot(d1, d2) / (len(d1) * len(d2)))))
  return Math.min(len(d1), len(d2)) * 0.2 * Math.sin(angle / 2)
}
/** SketchObject::fillet(GeoId, PosId, radius, trim, createCorner, chamfer): at a corner of two lines. */
export function filletAtPoint(d: Doc, g: number, pos: PointPos, radius: number, trimIt: boolean, createCorner: boolean, chamfer: boolean, move: Mover): boolean {
  const list = chooseFilletEdges(d, directlyCoincident(d, g, pos))
  if (list.length !== 2 || list[0][0] < 0 || list[1][0] < 0) return false
  const a = d.geometry[list[0][0]], b = d.geometry[list[1][0]]
  if (a.type !== 'LineSegment' || b.type !== 'LineSegment') return false
  const m1 = mul(add(a.start, a.end), 0.5), m2 = mul(add(b.start, b.end), 0.5)
  return fillet(d, list[0][0], list[1][0], m1, m2, radius, trimIt, createCorner, chamfer, move)
}
/** SketchObject::fillet(GeoId1, GeoId2, refPnt1, refPnt2, radius, trim, createCorner, chamfer), for two lines. */
export function fillet(d: Doc, geoId1: number, geoId2: number, ref1: XY, ref2: XY, radius: number, trimIt: boolean, createCorner: boolean, chamfer: boolean, move: Mover): boolean {
  if (!d.geometry[geoId1] || !d.geometry[geoId2]) return false
  // two geometries can only get filleted if they have a coincident point
  if (!d.constraints.some((c) => c.type === 'Coincident' && involvesGeoId(c, geoId1) && involvesGeoId(c, geoId2))) return false
  const l1 = d.geometry[geoId1], l2 = d.geometry[geoId2]
  if (l1.type !== 'LineSegment' || l2.type !== 'LineSegment') throw new Error('A fillet between curves other than two lines is not in this workbench yet')
  const center = filletCenter(l1, l2, radius, ref1, ref2)
  if (!center) return false
  const arc = lineFilletArc(l1, l2, center, radius)
  if (!arc) return false
  const corner = segIntersection(l1, l2)!
  const p1a = valueAt(arc, arc.start_angle)
  const dir1 = sub(l1.end, l1.start), dir2 = sub(l2.end, l2.start)
  const dist1 = projectToLine(sub(p1a, corner), dir1), dist2 = projectToLine(sub(p1a, corner), dir2)
  const pos1: PointPos = dot(sub(center, corner), dir1) > 0 ? START : END
  const pos2: PointPos = dot(sub(center, corner), dir2) > 0 ? START : END
  const reverse = len(dist1) < len(dist2)
  const filletId = d.geometry.length
  d.geometry = [...d.geometry, arc]
  let p1 = valueAt(arc, arc.start_angle), p2 = valueAt(arc, arc.end_angle)
  if (!reverse) [p1, p2] = [p2, p1]
  let filletPos1: PointPos = NONE, filletPos2: PointPos = NONE
  let g1 = geoId1, g2 = geoId2
  if (trimIt) {
    let newId1 = -1, newId2 = -1, swapped1 = false, swapped2 = false
    if (createCorner) {
      const coincidentCorner = !!coincidentPoints(d.constraints, g1, pos1).get(g2) && coincidentPoints(d.constraints, g1, pos1).get(g2) === pos2
      if (!coincidentCorner) {
        delConstraintOnPoint(d, g1, pos1, false)
        delConstraintOnPoint(d, g2, pos2, false)
        const del = d.constraints.map((c, i) => ((c.type === 'Distance' || c.type === 'Equal') && ((c.first === g1 && c.firstPos === NONE) || (c.first === g2 && c.firstPos === NONE)) ? i : -1)).filter((i) => i >= 0)
        delConstraints(d, del)
      } else {
        const splitCorner = (geoId: number, pos: PointPos, p: XY): [number, number, boolean] => {
          const highest = d.geometry.length - 1
          split(d, geoId, p)
          let newId = highest + 1, id = geoId
          const needsSwap = pos === START
          if (needsSwap) [newId, id] = [id, newId]
          d.geometry = d.geometry.map((x, i) => (i === newId ? { ...x, construction: true } : x))
          return [id, newId, needsSwap]
        }
        ;[g1, newId1, swapped1] = splitCorner(g1, pos1, p1)
        ;[g2, newId2, swapped2] = splitCorner(g2, pos2, p2)
      }
    } else {
      delConstraintOnPoint(d, g1, pos1, false)
      delConstraintOnPoint(d, g2, pos2, false)
    }
    filletPos1 = reverse ? START : END
    filletPos2 = reverse ? END : START
    for (const [g, pos, p] of [[g1, pos1, p1], [g2, pos2, p2]] as [number, PointPos, XY][]) {
      const out = move(d, g, pos, p)
      if (out) d.geometry = out
    }
    d.constraints = [...d.constraints, constraint('Tangent', g1, pos1, filletId, filletPos1), constraint('Tangent', g2, pos2, filletId, filletPos2)]
    if (createCorner) {
      const swap = (geoId: number, newId: number, swapped: boolean) => {
        if (swapped || newId < 0) return
        const temp = d.geometry.length
        d.constraints = d.constraints.map((c) => { const n = clone(c); substituteIndex(n, geoId, temp); substituteIndex(n, newId, geoId); substituteIndex(n, temp, newId); return n })
        const gs = [...d.geometry];[gs[geoId], gs[newId]] = [gs[newId], gs[geoId]]; d.geometry = gs
      }
      swap(g1, newId1, swapped1)
      swap(g2, newId2, swapped2)
    }
  }
  if (chamfer) {
    const lineId = d.geometry.length
    d.geometry = [...d.geometry, { type: 'LineSegment', start: p1, end: p2 }]
    d.constraints = [...d.constraints,
      trimIt ? constraint('Coincident', lineId, filletPos1, g1, pos1) : constraint('Coincident', lineId, filletPos1, filletId, START),
      trimIt ? constraint('Coincident', lineId, filletPos2, g2, pos2) : constraint('Coincident', lineId, filletPos2, filletId, END)]
    d.geometry = d.geometry.map((x, i) => (i === filletId ? { ...x, construction: true } : x))
  }
  return true
}
