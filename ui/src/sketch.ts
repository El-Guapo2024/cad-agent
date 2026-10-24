// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Sketcher/App/Constraint.cpp: 2008 Jürgen Riegel
//   src/Mod/Sketcher/App/ConstraintPyImp.cpp: 2010 Jürgen Riegel
//   src/Mod/Sketcher/App/SketchObject.cpp: 2008 Jürgen Riegel
//   src/Mod/Sketcher/Gui/TaskSketcherConstraints.cpp: 2009 Juergen Riegel
//   src/Mod/Sketcher/Gui/TaskSketcherElements.cpp: 2014 Abdullah Tahiri
//   src/Mod/Sketcher/Gui/EditModeConstraintCoinManager.cpp: 2021 Abdullah Tahiri
// The sketch as the Sketcher's UI edits it: geometry in the solver's form (planegcs-fake.ts / planegcs.ts), constraints
// with Sketcher::Constraint's own fields (First, FirstPos, ... Value, isDriving, Name), and SketchObject's helpers on
// them: points by (GeoId, PointPos), the vertex index, coincidence groups, element and constraint names, the value a
// dimension measures, its presentation string.
import type { Cons, Geo, XY } from './solver'
import { toNumber, userString, type Quantity } from './quantity'

export type { Geo, XY }
/** Sketcher::PointPos. */
export type PointPos = 0 | 1 | 2 | 3
export const NONE = 0, START = 1, END = 2, MID = 3
/** Sketcher::GeoEnum: GeoUndef, and the axes (the horizontal one's start is the root point). */
export const GEO_UNDEF = -2000, H_AXIS = -1, V_AXIS = -2, RT_PNT = -1
export type ConstraintType = 'Coincident' | 'Horizontal' | 'Vertical' | 'Parallel' | 'Tangent' | 'Distance' | 'DistanceX' | 'DistanceY'
  | 'Angle' | 'Perpendicular' | 'Radius' | 'Equal' | 'PointOnObject' | 'Symmetric' | 'InternalAlignment' | 'SnellsLaw' | 'Block'
  | 'Diameter' | 'Weight' | 'Group' | 'Text'
/** Sketcher::Constraint. */
export type Constraint = {
  type: ConstraintType
  first: number; firstPos: PointPos
  second: number; secondPos: PointPos
  third: number; thirdPos: PointPos
  value: number
  driving: boolean
  active: boolean
  name: string
  /** Where the datum label sits (Constraint::LabelDistance / LabelPosition), as the drag of a label leaves it. */
  labelDistance: number
  labelPosition: number
  /** Constraint::isInVirtualSpace. */
  virtual: boolean
}
export type SketchData = { geometry: Geo[]; constraints: Constraint[] }

export function constraint(type: ConstraintType, first: number, firstPos: PointPos = NONE, second = GEO_UNDEF, secondPos: PointPos = NONE,
  third = GEO_UNDEF, thirdPos: PointPos = NONE, value = 0): Constraint {
  return { type, first, firstPos, second, secondPos, third, thirdPos, value, driving: true, active: true, name: '',
    labelDistance: 10, labelPosition: type === 'Radius' || type === 'Diameter' ? 10 : 0, virtual: false }
}

const DIMENSIONAL: ConstraintType[] = ['Distance', 'DistanceX', 'DistanceY', 'Radius', 'Diameter', 'Angle', 'SnellsLaw', 'Weight']
/** Constraint::isDimensional. */
export const isDimensional = (c: Constraint) => DIMENSIONAL.includes(c.type)

/** Sketcher.Constraint(type, *args, value): ConstraintPyImp.cpp's argument forms, the value left out. */
export function toArgs(c: Constraint): number[] {
  const { type: t, first: f, firstPos: fp, second: s, secondPos: sp, third: th, thirdPos: tp } = c
  switch (t) {
    case 'Coincident': return [f, fp, s, sp]
    case 'Horizontal': case 'Vertical': return s === GEO_UNDEF ? [f] : [f, fp, s, sp]
    case 'Parallel': case 'Equal': return [f, s]
    case 'Perpendicular': case 'Tangent':
      if (th !== GEO_UNDEF) return [f, s, th, tp]
      if (fp === NONE && sp === NONE) return [f, s]
      if (sp === NONE) return [f, fp, s]
      return [f, fp, s, sp]
    case 'PointOnObject': return [f, fp, s]
    case 'Distance': case 'DistanceX': case 'DistanceY':
      if (s === GEO_UNDEF) return fp === NONE ? [f] : [f, fp]
      if (fp === NONE && sp === NONE) return [f, s]
      if (sp === NONE) return [f, fp, s]
      return [f, fp, s, sp]
    case 'Radius': case 'Diameter': case 'Weight': case 'Block': return [f]
    case 'Angle':
      if (s === GEO_UNDEF) return [f]
      if (th !== GEO_UNDEF) return [f, s, th, tp]
      if (fp === NONE && sp === NONE) return [f, s]
      return [f, fp, s, sp]
    case 'Symmetric': return tp === NONE ? [f, fp, s, sp, th] : [f, fp, s, sp, th, tp]
    default: return [f, fp, s, sp, th, tp]
  }
}
export function toCons(c: Constraint): Cons {
  const out: Cons = { type: c.type, args: toArgs(c) }
  if (isDimensional(c)) out.value = c.value
  if (!c.driving) out.driving = false
  if (c.name) out.name = c.name
  return out
}
/** ConstraintPy::PyInit's parsing, for the forms toArgs writes (an int argument where the value would be a GeoId). */
export function fromCons(k: Cons): Constraint {
  const t = k.type as ConstraintType, a = k.args, v = k.value ?? 0, P = (n: number) => n as PointPos
  let c: Constraint
  const hasValue = k.value !== undefined
  if (t === 'Coincident') c = constraint(t, a[0], P(a[1]), a[2], P(a[3]))
  else if (t === 'Symmetric') c = constraint(t, a[0], P(a[1]), a[2], P(a[3]), a[4], P(a[5] ?? 0))
  else if (t === 'PointOnObject') c = constraint(t, a[0], P(a[1]), a[2])
  else if (a.length === 1) c = constraint(t, a[0], NONE, GEO_UNDEF, NONE, GEO_UNDEF, NONE, v)
  else if (a.length === 2) {
    // (Geo, Geo) for the relations and an angle between lines; (Geo, Pos, value) for a point's DistanceX/Y
    if ((t === 'DistanceX' || t === 'DistanceY') && hasValue) c = constraint(t, a[0], P(a[1]), GEO_UNDEF, NONE, GEO_UNDEF, NONE, v)
    else c = constraint(t, a[0], NONE, a[1], NONE, GEO_UNDEF, NONE, v)
  } else if (a.length === 3) c = constraint(t, a[0], P(a[1]), a[2], NONE, GEO_UNDEF, NONE, v)
  else c = constraint(t, a[0], P(a[1]), a[2], P(a[3]), a[4] ?? GEO_UNDEF, P(a[5] ?? 0), v)
  if (k.driving === false) c.driving = false
  if (k.name) c.name = k.name
  return c
}

// ── points and vertices (SketchObject) ─────────────────────────────────────
/** SketchObject::getPoint(GeoId, PosId): the axes' start is the origin. */
export function getPoint(geo: Geo[], g: number, pos: PointPos): XY | null {
  if (g === H_AXIS || g === V_AXIS) return pos === START ? [0, 0] : null
  const e = geo[g]
  if (!e) return null
  switch (e.type) {
    case 'Point': return pos === START ? e.at : null
    case 'LineSegment': return pos === START ? e.start : pos === END ? e.end : null
    case 'Circle': return pos === MID ? e.center : null
    case 'ArcOfCircle':
      if (pos === MID) return e.center
      if (pos === START) return [e.center[0] + e.radius * Math.cos(e.start_angle), e.center[1] + e.radius * Math.sin(e.start_angle)]
      if (pos === END) return [e.center[0] + e.radius * Math.cos(e.end_angle), e.center[1] + e.radius * Math.sin(e.end_angle)]
      return null
  }
}
/** SketchObject::rebuildVertexIndex: every point of every geometry, in order. */
export function vertices(geo: Geo[]): [number, PointPos][] {
  const out: [number, PointPos][] = []
  geo.forEach((g, i) => {
    if (g.type === 'Point') out.push([i, START])
    else if (g.type === 'LineSegment') out.push([i, START], [i, END])
    else if (g.type === 'Circle') out.push([i, MID])
    else out.push([i, START], [i, END], [i, MID])
  })
  return out
}
/** SketchObject::getVertexIndexGeoPos. */
export function vertexOf(geo: Geo[], g: number, pos: PointPos): number {
  return vertices(geo).findIndex(([a, b]) => a === g && b === pos)
}
/** SketchObject::getCoincidenceGroups / getAllCoincidentPoints: the points the Coincident constraints tie to (g, pos). */
export function coincidentPoints(cons: Constraint[], g: number, pos: PointPos): Map<number, PointPos> {
  const groups: Map<number, PointPos>[] = []
  for (const c of cons) {
    if (c.type !== 'Coincident') continue
    const fi = groups.findIndex((m) => m.get(c.first) === c.firstPos), si = groups.findIndex((m) => m.get(c.second) === c.secondPos)
    if (fi >= 0 && si >= 0) { if (fi !== si) { groups[si].forEach((v, k) => groups[fi].set(k, v)); groups.splice(si, 1) } }
    else if (fi < 0 && si < 0) groups.push(new Map([[c.first, c.firstPos], [c.second, c.secondPos]]))
    else if (fi >= 0) groups[fi].set(c.second, c.secondPos)
    else groups[si].set(c.first, c.firstPos)
  }
  return groups.find((m) => m.get(g) === pos) ?? new Map()
}

// ── curves ───────────────────────────────────────────────────────────────────
export const isLine = (g: Geo | undefined): g is Extract<Geo, { type: 'LineSegment' }> => g?.type === 'LineSegment'
export const isCircle = (g: Geo | undefined): g is Extract<Geo, { type: 'Circle' }> => g?.type === 'Circle'
export const isArc = (g: Geo | undefined): g is Extract<Geo, { type: 'ArcOfCircle' }> => g?.type === 'ArcOfCircle'
export const isCircular = (g: Geo | undefined) => isCircle(g) || isArc(g)
/** EditModeGeometryCoinConverter: a curve as the polyline the view draws, SegmentsPerGeometry (50) segments for a full
 *  circle, an arc by its share of them. */
export function polyline(g: Geo, segments = 50): XY[] {
  if (g.type === 'Point') return [g.at]
  if (g.type === 'LineSegment') return [g.start, g.end]
  if (g.type === 'Circle') return Array.from({ length: segments + 1 }, (_, i) => { const t = (2 * Math.PI * i) / segments; return [g.center[0] + g.radius * Math.cos(t), g.center[1] + g.radius * Math.sin(t)] as XY })
  const range = g.end_angle - g.start_angle, n = Math.max(2, Math.ceil((segments * Math.abs(range)) / (2 * Math.PI)))
  return Array.from({ length: n + 1 }, (_, i) => { const t = g.start_angle + (range * i) / n; return [g.center[0] + g.radius * Math.cos(t), g.center[1] + g.radius * Math.sin(t)] as XY })
}
/** Part::GeomCurve::closestParameter then pointAtParameter, for the curves here. */
export function closestOnCurve(g: Geo, p: XY): XY {
  if (g.type === 'Point') return g.at
  if (g.type === 'LineSegment') {
    const d: XY = [g.end[0] - g.start[0], g.end[1] - g.start[1]], l2 = d[0] * d[0] + d[1] * d[1]
    const t = l2 ? Math.max(0, Math.min(1, ((p[0] - g.start[0]) * d[0] + (p[1] - g.start[1]) * d[1]) / l2)) : 0
    return [g.start[0] + t * d[0], g.start[1] + t * d[1]]
  }
  let a = Math.atan2(p[1] - g.center[1], p[0] - g.center[0])
  if (g.type === 'ArcOfCircle') {
    const norm = (x: number) => { while (x < g.start_angle) x += 2 * Math.PI; while (x > g.start_angle + 2 * Math.PI) x -= 2 * Math.PI; return x }
    a = norm(a)
    if (a > g.end_angle) { // outside the arc: the nearer end
      const ds = Math.abs(a - 2 * Math.PI - g.start_angle), de = Math.abs(a - g.end_angle)
      a = ds < de ? g.start_angle : g.end_angle
    }
  }
  return [g.center[0] + g.radius * Math.cos(a), g.center[1] + g.radius * Math.sin(a)]
}
/** Normalises an arc so that it runs counterclockwise from start_angle to a larger end_angle (Part::GeomArcOfCircle's
 *  emulateCCW range), start_angle in [-π, π). */
export function normalArc(center: XY, radius: number, a0: number, a1: number, construction?: boolean): Geo {
  let s = Math.atan2(Math.sin(a0), Math.cos(a0)), e = s + (a1 - a0)
  if (e < s) e += 2 * Math.PI * Math.ceil((s - e) / (2 * Math.PI))
  return { type: 'ArcOfCircle', center, radius, start_angle: s, end_angle: e, ...(construction ? { construction: true } : {}) }
}

// ── names ────────────────────────────────────────────────────────────────────
/** PropertyConstraintList::getConstraintName. */
export const constraintName = (c: Constraint, i: number) => c.name || `Constraint${i + 1}`
/** ViewProviderSketch's sub-element names. */
export const edgeName = (g: number) => (g === H_AXIS ? 'H_Axis' : g === V_AXIS ? 'V_Axis' : `Edge${g + 1}`)
export const vertexName = (v: number) => (v < 0 ? 'RootPoint' : `Vertex${v + 1}`)

const TYPE_NAMES: Partial<Record<ConstraintType, string>> = {
  Horizontal: 'Horizontal', Vertical: 'Vertical', Coincident: 'Coincident', PointOnObject: 'PointOnObject', Parallel: 'Parallel',
  Perpendicular: 'Perpendicular', Tangent: 'Tangent', Equal: 'Equal', Symmetric: 'Symmetric', Block: 'Lock', Distance: 'Distance',
  DistanceX: 'DistanceX', DistanceY: 'DistanceY', Radius: 'Radius', Diameter: 'Diameter', Angle: 'Angle', Weight: 'Weight', SnellsLaw: 'Snell',
  InternalAlignment: 'Alignment',
}
/** TaskSketcherConstraints' ConstraintItem::getName: the name, or "N-Type". */
export const listName = (c: Constraint, i: number) => c.name || `${i + 1}-${TYPE_NAMES[c.type] ?? 'Constraint'}`

const LENGTH: Quantity['dims'] = [1, 0, 0, 0, 0, 0, 0, 0], ANGLE: Quantity['dims'] = [0, 0, 0, 0, 0, 0, 0, 1]
/** Constraint::getPresentationValue: a length in mm, an angle in degrees, formatted QuantityFormat::Default at
 *  precision 6 (%g) in the user's unit system (Quantity::getUserString). */
export function presentationValue(c: Constraint): string {
  if (c.type === 'SnellsLaw' || c.type === 'Weight') return toNumber(c.value, 'Default', 6)
  const angle = c.type === 'Angle'
  const q: Quantity = { value: angle ? (c.value * 180) / Math.PI : c.value, dims: angle ? ANGLE : LENGTH }
  const { factor, unit } = userString(q)
  const bare = !unit || ['°', '″', '′', '"', "'"].includes(unit)
  return `${toNumber(q.value / factor, 'Default', 6)}${bare ? '' : ' '}${unit}`
}
/** TaskSketcherConstraints' ConstraintItem::data(DisplayRole). */
export function listText(c: Constraint, i: number): string {
  const name = listName(c, i)
  return isDimensional(c) && c.type !== 'SnellsLaw' ? `${name} (${presentationValue(c)})` : name
}
/** The icon TaskSketcherConstraints shows for a constraint (ConstraintItem::data, DecorationRole). */
export function listIcon(c: Constraint): string {
  const driven = !c.driving
  switch (c.type) {
    case 'Horizontal': return 'Constraint_Horizontal'
    case 'Vertical': return 'Constraint_Vertical'
    case 'Coincident': return 'Constraint_PointOnPoint'
    case 'Block': return 'Constraint_Block'
    case 'PointOnObject': return 'Constraint_PointOnObject'
    case 'Parallel': return 'Constraint_Parallel'
    case 'Perpendicular': return 'Constraint_Perpendicular'
    case 'Tangent': return 'Constraint_Tangent'
    case 'Equal': return 'Constraint_EqualLength'
    case 'Symmetric': return 'Constraint_Symmetric'
    case 'Distance': return driven ? 'Constraint_Length_Driven' : 'Constraint_Length'
    case 'DistanceX': return driven ? 'Constraint_HorizontalDistance_Driven' : 'Constraint_HorizontalDistance'
    case 'DistanceY': return driven ? 'Constraint_VerticalDistance_Driven' : 'Constraint_VerticalDistance'
    case 'Radius': case 'Weight': return driven ? 'Constraint_Radius_Driven' : 'Constraint_Radius'
    case 'Diameter': return driven ? 'Constraint_Diameter_Driven' : 'Constraint_Diameter'
    case 'Angle': return driven ? 'Constraint_InternalAngle_Driven' : 'Constraint_InternalAngle'
    case 'SnellsLaw': return driven ? 'Constraint_SnellsLaw_Driven' : 'Constraint_SnellsLaw'
    default: return 'Constraint_InternalAlignment'
  }
}
/** TaskSketcherElements' label: "N-Line", "-Construction" when the naming box is on. */
export function elementText(g: Geo, i: number): string {
  const base = g.type === 'Point' ? 'Point' : g.type === 'LineSegment' ? 'Line' : g.type === 'Circle' ? 'Circle' : 'Arc'
  return `${i + 1}-${base}`
}

// ── what a dimension measures ───────────────────────────────────────────────
const dist = (a: XY, b: XY) => Math.hypot(b[0] - a[0], b[1] - a[1])
/** Distance of p from the line through a and b. */
export function distToLine(p: XY, a: XY, b: XY): number {
  const d: XY = [b[0] - a[0], b[1] - a[1]], l = Math.hypot(d[0], d[1])
  return l ? Math.abs(d[0] * (p[1] - a[1]) - d[1] * (p[0] - a[0])) / l : dist(p, a)
}
function lineOf(geo: Geo[], g: number): [XY, XY] | null {
  if (g === H_AXIS) return [[0, 0], [1, 0]]
  if (g === V_AXIS) return [[0, 0], [0, 1]]
  const e = geo[g]
  return isLine(e) ? [e.start, e.end] : null
}
/** The value a dimensional constraint has in the sketch as it is (SketchObject::calculateConstraintValue's cases): what
 *  a new dimension starts at, and what a reference dimension shows. */
export function measure(geo: Geo[], c: Constraint): number {
  const P = (g: number, p: PointPos) => getPoint(geo, g, p)
  switch (c.type) {
    case 'Distance': {
      if (c.second === GEO_UNDEF) { const e = geo[c.first]; if (isLine(e)) return dist(e.start, e.end); if (isCircular(e)) return (e as { radius: number }).radius; return 0 }
      if (c.firstPos !== NONE && c.secondPos !== NONE) { const a = P(c.first, c.firstPos), b = P(c.second, c.secondPos); return a && b ? dist(a, b) : 0 }
      if (c.firstPos !== NONE) {
        const a = P(c.first, c.firstPos)!, l = lineOf(geo, c.second)
        if (l) return distToLine(a, l[0], l[1])
        const e = geo[c.second] as { center: XY; radius: number }
        return Math.abs(dist(a, e.center) - e.radius)
      }
      const e1 = geo[c.first], e2 = geo[c.second]
      if (isCircular(e1) && isCircular(e2)) { const a = e1 as { center: XY; radius: number }, b = e2 as { center: XY; radius: number }; const d = dist(a.center, b.center); return d > a.radius + b.radius ? d - a.radius - b.radius : Math.abs(a.radius - b.radius) - d }
      const [l, ci] = isLine(e1) ? [c.first, c.second] : [c.second, c.first], ll = lineOf(geo, l)!, cc = geo[ci] as { center: XY; radius: number }
      return distToLine(cc.center, ll[0], ll[1]) - cc.radius
    }
    case 'DistanceX': case 'DistanceY': {
      const k = c.type === 'DistanceX' ? 0 : 1
      if (c.second === GEO_UNDEF) {
        if (c.firstPos === NONE) { const l = lineOf(geo, c.first)!; return l[1][k] - l[0][k] }
        return P(c.first, c.firstPos)![k]
      }
      return P(c.second, c.secondPos)![k] - P(c.first, c.firstPos)![k]
    }
    case 'Radius': return (geo[c.first] as { radius: number }).radius
    case 'Diameter': return 2 * (geo[c.first] as { radius: number }).radius
    case 'Angle': {
      const ang = (d1: XY, d2: XY) => Math.atan2(d1[0] * d2[1] - d1[1] * d2[0], d1[0] * d2[0] + d1[1] * d2[1])
      if (c.second === GEO_UNDEF) {
        const e = geo[c.first]
        if (isArc(e)) return e.end_angle - e.start_angle
        const l = lineOf(geo, c.first)!; return Math.atan2(l[1][1] - l[0][1], l[1][0] - l[0][0])
      }
      const l1 = lineOf(geo, c.first)!, l2 = lineOf(geo, c.second)!
      if (c.firstPos === NONE) return ang([l1[1][0] - l1[0][0], l1[1][1] - l1[0][1]], [l2[1][0] - l2[0][0], l2[1][1] - l2[0][1]])
      const dir = (l: [XY, XY], pos: PointPos): XY => (pos === END ? [l[0][0] - l[1][0], l[0][1] - l[1][1]] : [l[1][0] - l[0][0], l[1][1] - l[0][1]])
      return ang(dir(l1, c.firstPos), dir(l2, c.secondPos))
    }
    default: return c.value
  }
}
