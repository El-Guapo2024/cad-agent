// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Part/App/Geometry.cpp: 2008 Werner Mayer
//   src/Mod/Sketcher/App/SketchObjectGeometry.cpp: 2008 Jürgen Riegel
//   src/Mod/Sketcher/App/SketchGeometry.cpp: 2025 Werner Mayer
//   src/Mod/Sketcher/Gui/EditModeGeometryCoinConverter.cpp: 2021 Abdullah Tahiri
//   src/Mod/Sketcher/App/planegcs/Geo.cpp: 2014 Victor Titov (DeepSOIC)
// The Sketcher's conics and B-splines in the browser: a point at a parameter as OpenCascade's ElCLib and
// Geom_BSplineCurve give it (the solver, ui/planegcs, holds the same numbers), the polyline the edit mode draws
// (EditModeGeometryCoinConverter: 50 segments a conic, 50 a knot span of a B-spline), the nearest point on a curve, and
// the internal geometry SketchObject::exposeInternalGeometry adds to a conic or a B-spline (the axes and foci, the pole
// circles with the first weight and equal weights, the knot points).
import type { Geo, XY } from './solver'

export type Ellipse = Extract<Geo, { type: 'Ellipse' }>
export type ArcOfEllipse = Extract<Geo, { type: 'ArcOfEllipse' }>
export type ArcOfHyperbola = Extract<Geo, { type: 'ArcOfHyperbola' }>
export type ArcOfParabola = Extract<Geo, { type: 'ArcOfParabola' }>
export type BSpline = Extract<Geo, { type: 'BSplineCurve' }>
export type Conic = Ellipse | ArcOfEllipse | ArcOfHyperbola | ArcOfParabola
export type ConicArc = ArcOfEllipse | ArcOfHyperbola | ArcOfParabola

export const isConic = (g: Geo | undefined): g is Conic =>
  !!g && (g.type === 'Ellipse' || g.type === 'ArcOfEllipse' || g.type === 'ArcOfHyperbola' || g.type === 'ArcOfParabola')
export const isConicArc = (g: Geo | undefined): g is ConicArc =>
  !!g && (g.type === 'ArcOfEllipse' || g.type === 'ArcOfHyperbola' || g.type === 'ArcOfParabola')
export const isEllipse = (g: Geo | undefined): g is Ellipse => g?.type === 'Ellipse'
export const isBSpline = (g: Geo | undefined): g is BSpline => g?.type === 'BSplineCurve'
/** Ellipses and arcs of ellipse (what the ellipse's internal alignment applies to). */
export const isElliptic = (g: Geo | undefined): g is Ellipse | ArcOfEllipse => g?.type === 'Ellipse' || g?.type === 'ArcOfEllipse'

const sub = (a: XY, b: XY): XY => [a[0] - b[0], a[1] - b[1]]
const add = (a: XY, b: XY): XY => [a[0] + b[0], a[1] + b[1]]
const mul = (a: XY, k: number): XY => [a[0] * k, a[1] * k]
const len = (a: XY) => Math.hypot(a[0], a[1])
const unit = (a: XY): XY => { const l = len(a); return l ? [a[0] / l, a[1] / l] : [1, 0] }

// ── conics (gp_Ax2 with the normal +Z: Y is X turned a quarter counter-clockwise) ───────────────────────────────
/** The conic's X direction (Part's XAxis: the major axis, towards a parabola's focus) and Y = Z ^ X. */
export function conicAxes(g: Conic): { x: XY; y: XY } {
  const x = unit(g.x_axis ?? [1, 0])
  return { x, y: [-x[1], x[0]] }
}
/** ElCLib's EllipseValue / HyperbolaValue / ParabolaValue: the conic at parameter u. */
export function conicValue(g: Conic, u: number): XY {
  const { x, y } = conicAxes(g)
  let a1: number, a2: number
  if (g.type === 'ArcOfHyperbola') { a1 = g.major_radius * Math.cosh(u); a2 = g.minor_radius * Math.sinh(u) }
  else if (g.type === 'ArcOfParabola') { a1 = g.focal === 0 ? 0 : (u * u) / (4 * g.focal); a2 = u }
  else { a1 = g.major_radius * Math.cos(u); a2 = g.minor_radius * Math.sin(u) }
  return [a1 * x[0] + a2 * y[0] + g.center[0], a1 * x[1] + a2 * y[1] + g.center[1]]
}
/** The conic's first derivative at u. */
export function conicTangent(g: Conic, u: number): XY {
  const { x, y } = conicAxes(g)
  let a1: number, a2: number
  if (g.type === 'ArcOfHyperbola') { a1 = g.major_radius * Math.sinh(u); a2 = g.minor_radius * Math.cosh(u) }
  else if (g.type === 'ArcOfParabola') { a1 = g.focal === 0 ? 0 : u / (2 * g.focal); a2 = 1 }
  else { a1 = -g.major_radius * Math.sin(u); a2 = g.minor_radius * Math.cos(u) }
  return [a1 * x[0] + a2 * y[0], a1 * x[1] + a2 * y[1]]
}
/** The parameter range: [0, 2π] for an ellipse, the trim of an arc. */
export function conicRange(g: Conic): [number, number] {
  return g.type === 'Ellipse' ? [0, 2 * Math.PI] : [g.start_angle, g.end_angle]
}
/** An ellipse's or hyperbola's first focus (on the X axis), a parabola's focus. */
export function focus1(g: Conic): XY {
  const { x } = conicAxes(g)
  if (g.type === 'ArcOfParabola') return add(g.center, mul(x, g.focal))
  const a = g.major_radius, b = g.minor_radius
  const d = g.type === 'ArcOfHyperbola' ? Math.sqrt(a * a + b * b) : Math.sqrt(Math.max(0, a * a - b * b))
  return add(g.center, mul(x, d))
}

// ── B-splines (Geom_BSplineCurve; GCS::BSpline's evaluation) ───────────────────────────────────────────────────
/** The knot sequence with each knot repeated by its multiplicity, padded at both ends for a periodic curve as
 *  GCS::BSpline::setupFlattenedKnots pads it. */
export function flatKnots(b: BSpline): number[] {
  const fk: number[] = []
  b.knots.forEach((k, i) => { for (let m = 0; m < b.mults[i]; m++) fk.push(k) })
  if (b.periodic) {
    const period = b.knots[b.knots.length - 1] - b.knots[0], c = b.degree + 1 - b.mults[0]
    const front = fk.slice(fk.length - b.mults[b.mults.length - 1] - c, fk.length - b.mults[b.mults.length - 1]).map((k) => k - period)
    const back = fk.slice(b.mults[0], b.mults[0] + c).map((k) => k + period)
    return [...front, ...fk, ...back]
  }
  return fk
}
/** Geom_BSplineCurve::FirstParameter and LastParameter. */
export function bsplineRange(b: BSpline): [number, number] {
  if (b.periodic) return [b.knots[0], b.knots[b.knots.length - 1]]
  const fk = flatKnots(b)
  return [fk[b.degree], fk[fk.length - 1 - b.degree]]
}
const weightsOf = (b: BSpline) => b.weights && b.weights.length === b.poles.length ? b.weights : b.poles.map(() => 1)
/** The B-spline at u and its first derivative: de Boor on the homogeneous poles of the knot span holding u. */
export function bsplineD1(b: BSpline, u: number): { p: XY; d: XY } {
  const p = b.degree, fk = flatKnots(b), n = b.poles.length, w = weightsOf(b)
  let k = p
  while (k + 1 < fk.length - p - 1 && fk[k + 1] <= u) k++
  const start = k - p
  const at = (i: number) => (start + i) % n
  const spline = (deg: number, d: number[]) => {
    for (let r = 1; r <= deg; r++) for (let j = deg; j > r - 1; j--) {
      const alpha = (u - fk[j + k - deg]) / (fk[j + 1 + k - r] - fk[j + k - deg])
      d[j] = (1 - alpha) * d[j - 1] + alpha * d[j]
    }
    return deg < d.length ? d[deg] : 0
  }
  const vals = (f: (i: number) => number) => spline(p, Array.from({ length: p + 1 }, (_, i) => f(at(i))))
  const xs = vals((i) => b.poles[i][0] * w[i]), ys = vals((i) => b.poles[i][1] * w[i]), ws = vals((i) => w[i])
  const slope = (f: (i: number) => number) => p * spline(p - 1, Array.from({ length: p }, (_, j) => {
    const i = j + 1
    return (f(at(i)) - f(at(i - 1))) / (fk[start + i + p] - fk[start + i])
  }))
  const xd = slope((i) => b.poles[i][0] * w[i]), yd = slope((i) => b.poles[i][1] * w[i]), wd = slope((i) => w[i])
  return { p: [xs / ws, ys / ws], d: [(ws * xd - wd * xs) / ws / ws, (ws * yd - wd * ys) / ws / ws] }
}
export const bsplineValue = (b: BSpline, u: number): XY => bsplineD1(b, u).p
/** Geom_BSplineCurve::StartPoint / EndPoint: the end pole of a clamped curve, else the curve at its end parameter. */
export function bsplineStart(b: BSpline): XY { return b.mults[0] === b.degree + 1 ? b.poles[0] : bsplineValue(b, bsplineRange(b)[0]) }
export function bsplineEnd(b: BSpline): XY { return b.mults[b.mults.length - 1] === b.degree + 1 ? b.poles[b.poles.length - 1] : bsplineValue(b, bsplineRange(b)[1]) }

// ── the curve as one function of its parameter ──────────────────────────────────────────────────────────────────
type Param = { range: [number, number]; at(u: number): XY; tangent(u: number): XY }
/** A curve's parameterisation, for the curves here (a line by length, a circle by angle, as OpenCascade's). */
export function parameterised(g: Geo): Param | null {
  switch (g.type) {
    case 'LineSegment': {
      const d = unit(sub(g.end, g.start))
      return { range: [0, len(sub(g.end, g.start))], at: (u) => add(g.start, mul(d, u)), tangent: () => d }
    }
    case 'Circle': case 'ArcOfCircle': {
      const r = g.radius, c = g.center
      return { range: g.type === 'Circle' ? [0, 2 * Math.PI] : [g.start_angle, g.end_angle],
        at: (u) => [c[0] + r * Math.cos(u), c[1] + r * Math.sin(u)], tangent: (u) => [-r * Math.sin(u), r * Math.cos(u)] }
    }
    case 'Ellipse': case 'ArcOfEllipse': case 'ArcOfHyperbola': case 'ArcOfParabola':
      return { range: conicRange(g), at: (u) => conicValue(g, u), tangent: (u) => conicTangent(g, u) }
    case 'BSplineCurve':
      return { range: bsplineRange(g), at: (u) => bsplineValue(g, u), tangent: (u) => bsplineD1(g, u).d }
    default: return null
  }
}
/** EditModeGeometryCoinConverter's polyline of a conic (CurvedEdgeCountSegments, 50) or a B-spline (50 a knot span). */
export function curvePolyline(g: Geo, segments = 50): XY[] | null {
  const c = parameterised(g)
  if (!c || g.type === 'LineSegment' || g.type === 'Circle' || g.type === 'ArcOfCircle') return null
  const n = g.type === 'BSplineCurve' ? segments * Math.max(1, g.knots.length - 1) : segments
  const [u0, u1] = c.range, step = (u1 - u0) / n
  const out: XY[] = []
  for (let i = 0; i < n; i++) out.push(c.at(u0 + i * step))
  out.push(g.type === 'Ellipse' ? c.at(u0) : c.at(u1))
  return out
}
/** GeomCurve::closestParameter: the nearest orthogonal projection of p within the curve's range (the roots of
 *  (C(u) - p)·C'(u), bracketed on a sampling and halved to the bit); without one, the nearer end. */
export function closestParameter(g: Geo, p: XY): number | null {
  const c = parameterised(g)
  if (!c) return null
  const [u0, u1] = c.range
  const f = (u: number) => { const q = c.at(u), t = c.tangent(u); return (q[0] - p[0]) * t[0] + (q[1] - p[1]) * t[1] }
  const d2 = (u: number) => { const q = c.at(u); return (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2 }
  const n = g.type === 'LineSegment' ? 1 : g.type === 'BSplineCurve' ? 32 * g.poles.length : 64
  let best: number | null = null, bestD = Infinity
  const consider = (u: number) => { const d = d2(u); if (d < bestD) { bestD = d; best = u } }
  let ua = u0, fa = f(u0)
  for (let i = 1; i <= n; i++) {
    const ub = i === n ? u1 : u0 + ((u1 - u0) * i) / n, fb = f(ub)
    if (fa === 0) consider(ua)
    else if ((fa < 0) !== (fb < 0) && fb !== 0) {
      let lo = ua, hi = ub, flo = fa
      for (let it = 0; it < 200; it++) {
        const mid = lo + (hi - lo) / 2
        if (mid <= lo || mid >= hi) break
        const fm = f(mid)
        if (fm === 0) { lo = hi = mid; break }
        if ((fm < 0) === (flo < 0)) { lo = mid; flo = fm } else hi = mid
      }
      consider(Math.abs(f(lo)) <= Math.abs(f(hi)) ? lo : hi)
    }
    ua = ub; fa = fb
  }
  if (fa === 0) consider(ua)
  if (best !== null) return best
  return d2(u1) < d2(u0) ? u1 : u0
}

// ── exposeInternalGeometry (SketchObjectGeometry.cpp) ───────────────────────────────────────────────────────────
export type Alignment = 'EllipseMajorDiameter' | 'EllipseMinorDiameter' | 'EllipseFocus1' | 'EllipseFocus2' | 'HyperbolaMajor' | 'HyperbolaMinor'
  | 'HyperbolaFocus' | 'ParabolaFocus' | 'BSplineControlPoint' | 'BSplineKnotPoint' | 'ParabolaFocalAxis'
/** An internal-alignment constraint as the case for exposeInternalGeometry needs it: the aligned geometry, the parent,
 *  the alignment and, for a pole or a knot, its index. */
export type AlignmentRef = { first: number; second: number; alignment: Alignment; index: number }
/** What exposeInternalGeometry adds: construction geometry, then InternalAlignment constraints (first, firstPos, the
 *  parent, the alignment, the index), Weight and Equal constraints. */
export type Exposed = {
  geometry: Geo[]
  alignments: { first: number; firstPos: 0 | 1 | 3; second: number; alignment: Alignment; index: number }[]
  others: { type: 'Weight' | 'Equal'; first: number; second?: number; value?: number }[]
  /** The order the constraints come in (index into alignments, or -1 - index into others). */
  order: number[]
}
/** SketchObject::exposeInternalGeometry(GeoId): the internal geometry of the conic or B-spline geoId that the sketch's
 *  InternalAlignment constraints do not already have, numbered from firstNew (getHighestCurveIndex() + 1). */
export function exposeInternalGeometry(geometry: Geo[], existing: AlignmentRef[], geoId: number, isWeighted: (circle: number) => boolean): Exposed | null {
  const g = geometry[geoId]
  const out: Exposed = { geometry: [], alignments: [], others: [], order: [] }
  if (!g) return null
  const have = existing.filter((c) => c.second === geoId)
  const has = (a: Alignment) => have.some((c) => c.alignment === a)
  let next = geometry.length
  const line = (a: XY, b: XY): Geo => ({ type: 'LineSegment', start: a, end: b, construction: true })
  const point = (a: XY): Geo => ({ type: 'Point', at: a, construction: true })
  const align = (geo: Geo, firstPos: 0 | 1 | 3, alignment: Alignment, index = -1) => {
    out.geometry.push(geo)
    out.order.push(out.alignments.length)
    out.alignments.push({ first: next++, firstPos, second: geoId, alignment, index })
  }
  if (g.type === 'Ellipse' || g.type === 'ArcOfEllipse') {
    if (have.some((c) => !['EllipseMajorDiameter', 'EllipseMinorDiameter', 'EllipseFocus1', 'EllipseFocus2'].includes(c.alignment))) return null
    const c = g.center, a = g.major_radius, b = g.minor_radius, { x } = conicAxes(g), y: XY = [-x[1], x[0]]
    const df = Math.sqrt(a * a - b * b)
    if (!has('EllipseMajorDiameter')) align(line(add(c, mul(x, a)), sub(c, mul(x, a))), 0, 'EllipseMajorDiameter')
    if (!has('EllipseMinorDiameter')) align(line(add(c, mul(y, b)), sub(c, mul(y, b))), 0, 'EllipseMinorDiameter')
    if (!has('EllipseFocus1')) align(point(add(c, mul(x, df))), 1, 'EllipseFocus1')
    if (!has('EllipseFocus2')) align(point(sub(c, mul(x, df))), 1, 'EllipseFocus2')
    return out
  }
  if (g.type === 'ArcOfHyperbola') {
    if (have.some((c) => !['HyperbolaMajor', 'HyperbolaMinor', 'HyperbolaFocus'].includes(c.alignment))) return null
    const c = g.center, a = g.major_radius, b = g.minor_radius, { x } = conicAxes(g), y: XY = [-x[1], x[0]]
    const majP = add(c, mul(x, a)), majN = sub(c, mul(x, a))
    if (!has('HyperbolaMajor')) align(line(majP, majN), 0, 'HyperbolaMajor')
    if (!has('HyperbolaMinor')) align(line(add(majP, mul(y, b)), sub(majP, mul(y, b))), 0, 'HyperbolaMinor')
    if (!has('HyperbolaFocus')) align(point(add(c, mul(x, Math.sqrt(a * a + b * b)))), 1, 'HyperbolaFocus')
    return out
  }
  if (g.type === 'ArcOfParabola') {
    if (have.some((c) => !['ParabolaFocus', 'ParabolaFocalAxis'].includes(c.alignment))) return null
    const f = focus1(g)
    if (!has('ParabolaFocus')) align(point(f), 1, 'ParabolaFocus')
    if (!has('ParabolaFocalAxis')) align(line(g.center, f), 0, 'ParabolaFocalAxis')
    return out
  }
  if (g.type === 'BSplineCurve') {
    if (have.some((c) => c.alignment !== 'BSplineControlPoint' && c.alignment !== 'BSplineKnotPoint')) return null
    const poles = g.poles, w = weightsOf(g)
    const cp = poles.map((_, i) => have.find((c) => c.alignment === 'BSplineControlPoint' && c.index === i)?.first ?? null)
    const kp = g.knots.map((_, i) => have.find((c) => c.alignment === 'BSplineKnotPoint' && c.index === i)?.first ?? null)
    let firstWeighted = cp[0] !== null && isWeighted(cp[0])
    const r = len(sub(poles[1], poles[0])) / 6 // distance_p0_p1 / 6, for visual purposes only
    for (let i = 0; i < poles.length; i++) {
      if (cp[i] !== null) continue
      const id = next
      align({ type: 'Circle', center: poles[i], radius: r, construction: true }, 3, 'BSplineControlPoint', i)
      if (i === 0) {
        cp[0] = id
        if (w[0] === 1.0) { out.order.push(-1 - out.others.length); out.others.push({ type: 'Weight', first: id, value: w[0] }); firstWeighted = true }
        continue
      }
      if (firstWeighted && w[0] === w[i]) { out.order.push(-1 - out.others.length); out.others.push({ type: 'Equal', first: id, second: cp[0]! }) }
    }
    for (let i = 0; i < g.knots.length; i++) {
      if (kp[i] !== null) continue
      align(point(bsplineValue(g, g.knots[i])), 1, 'BSplineKnotPoint', i)
    }
    return out
  }
  return null
}
