// SPDX-License-Identifier: LGPL-2.1-or-later
// Follows FreeCAD (https://github.com/FreeCAD/FreeCAD, commit 3160daf1e2b6), copyright of the files below (each is
// LGPL-2.0-or-later or LGPL-2.1-or-later as it states; ui/NOTICE has them all):
//   src/Mod/Sketcher/App/SketchObjectOperations.cpp: 2008 Jürgen Riegel
//   src/Mod/Sketcher/App/SketchObjectConstraints.cpp: 2008 Jürgen Riegel
//   src/Mod/Sketcher/App/SketchObjectPyImp.cpp: 2010 Jürgen Riegel
//   src/Mod/Part/App/Geometry.cpp: 2008 Werner Mayer
//   src/Base/Vector3D.cpp: 2005 Imetric 3D GmbH
//   src/Mod/Sketcher/Gui/DrawSketchHandlerTranslate.h: 2022 Boyer Pierre-Louis
//   src/Mod/Sketcher/Gui/DrawSketchHandlerRotate.h: 2022 Boyer Pierre-Louis
//   src/Mod/Sketcher/Gui/DrawSketchHandlerScale.h: 2022 Boyer Pierre-Louis
// SketchObject's transform operations, as the Sketcher's Copy, Clone, Move, Rectangular Array, Symmetry and Remove
// Axes Alignment tools call them (sketch.addSymmetric(geoIds, refGeoId, refPosId), addCopy(geoIds, vector, clone),
// addMove(geoIds, vector), addRectangularArray(geoIds, vector, clone, rows, cols, constrainDisplacement, perpScale),
// removeAxesAlignment(geoIds)): the geometry they make (getSymmetric's mirror about a line or a point, the
// displaced copies of addCopy) and which constraints the copies inherit. Ported as FreeCAD 26.3 has them, the parts
// that look unintended included (addCopy's construction line for a plain copy, its three-element constraints), so
// that a sketch edited here is the sketch FreeCAD makes.
import type { Geo, XY } from './solver'
import { type Constraint, type PointPos, NONE, START, END, MID, GEO_UNDEF, H_AXIS, V_AXIS, RT_PNT, constraint, getPoint, coincidentPoints } from './sketch'

export type Doc = { geometry: Geo[]; constraints: Constraint[] }

const TWO_PI = 2 * Math.PI
const CONFUSION = 1e-7, ANGULAR = 1e-12, PCONFUSION = CONFUSION * 0.01
const sub = (a: XY, b: XY): XY => [a[0] - b[0], a[1] - b[1]], add = (a: XY, b: XY): XY => [a[0] + b[0], a[1] + b[1]]
const mul = (a: XY, k: number): XY => [a[0] * k, a[1] * k], dot = (a: XY, b: XY) => a[0] * b[0] + a[1] * b[1]
const len = (a: XY) => Math.hypot(a[0], a[1])
const unit = (a: XY): XY => { const l = len(a); return l ? [a[0] / l, a[1] / l] : [1, 0] }
/** Base::fmod: the remainder, made positive. */
const fmod = (n: number, d: number) => { const m = n % d; return m >= 0 ? m : m + d }
/** Base::Vector3d::Perpendicular(base, dir): the foot of the perpendicular from p onto the line. */
const perpendicular = (p: XY, base: XY, dir: XY): XY => { const t = dot(sub(p, base), dir) / dot(dir, dir); return add(base, mul(dir, t)) }
/** Geom_TrimmedCurve::SetTrim on a periodic curve (ElCLib::AdjustPeriodic). */
function setTrimPeriodic(u1: number, u2: number): [number, number] {
  const preci = Math.min(Math.abs(u2 - u1) / 2, PCONFUSION)
  u1 -= Math.floor(u1 / TWO_PI) * TWO_PI
  if (TWO_PI - u1 < preci) u1 -= TWO_PI
  u2 -= Math.floor((u2 - u1) / TWO_PI) * TWO_PI
  if (u2 - u1 < preci) u2 += TWO_PI
  return [u1, u2]
}
/** GeomEllipse / GeomArcOfConic setMajorAxisDir and setXAxisDir: a zero vector keeps the old direction. */
const axisDir = (newdir: XY, old: XY): XY => (dot(newdir, newdir) < CONFUSION * CONFUSION ? old : unit(newdir))
/** Geometry::copy for the arcs of conics: the cached end points go (the solver's JSON may carry them). */
function stripEnds<G extends Geo>(g: G): G {
  const { start_point: _s, end_point: _e, ...rest } = g as G & { start_point?: XY; end_point?: XY }
  void _s; void _e
  return rest as G
}

/** SketchObject::getGeometry: the axes are lines from the origin along X and Y; the external geometry is reachable at
 *  its GeoIds when the array carries it (sketch.ts's withExternal). */
function geometryAt(d: Doc, g: number): Geo | undefined {
  if (g === H_AXIS) return { type: 'LineSegment', start: [0, 0], end: [1, 0] }
  if (g === V_AXIS) return { type: 'LineSegment', start: [0, 0], end: [0, 1] }
  return d.geometry[g]
}
/** GeometryFacade::isInternalAligned: the geometry is the first element of an InternalAlignment. */
const isInternalAligned = (d: Doc, g: number) => d.constraints.some((c) => c.type === 'InternalAlignment' && c.first === g)
/** The geometry an internal-aligned element defines (the second of its InternalAlignment), else GeoUndef. */
function definedGeometry(d: Doc, g: number) {
  const c = d.constraints.find((k) => k.type === 'InternalAlignment' && k.first === g)
  return c ? c.second : GEO_UNDEF
}
const pointOf = (d: Doc, g: number, pos: PointPos): XY => getPoint(d.geometry, g, pos) ?? [0, 0]

// ── mirror (SketchObject::getSymmetric) ──────────────────────────────────────────────────────────────────────────
export type Symmetric = { geometry: Geo[]; geoIdMap: Map<number, number>; inverted: Map<number, boolean> }
/** SketchObject::getSymmetric: the mirror images of the geometry about the line refGeoId (refPosId none) or the point
 *  (refGeoId, refPosId), the GeoId each gets (geoIdMap, from the next free one) and whether its start and end swap. */
export function getSymmetric(d: Doc, geoIdList: number[], refGeoId: number, refPosId: PointPos = NONE): Symmetric {
  const out: Geo[] = [], geoIdMap = new Map<number, number>(), inverted = new Map<number, boolean>()
  let cgeoid = d.geometry.length
  // internal geometry only goes with the geometry it defines
  const shouldCopy = (g: number) => !isInternalAligned(d, g) || geoIdList.includes(definedGeometry(d, g))
  const done = (g: number, sym: Geo, inv: boolean | null) => {
    if (inv !== null && !inverted.has(g)) inverted.set(g, inv)
    out.push(sym)
    if (!geoIdMap.has(g)) geoIdMap.set(g, cgeoid)
    cgeoid++
  }
  if (refPosId === NONE) {
    const ref = geometryAt(d, refGeoId)
    if (ref?.type !== 'LineSegment') return { geometry: [], geoIdMap, inverted }
    const base = ref.start, vectline = sub(ref.end, ref.start)
    const m = (p: XY): XY => add(p, mul(sub(perpendicular(p, base, vectline), p), 2))
    for (const geoId of geoIdList) {
      const geo = geometryAt(d, geoId)
      if (!geo || !shouldCopy(geoId)) continue
      switch (geo.type) {
        case 'LineSegment': done(geoId, { ...geo, start: m(geo.start), end: m(geo.end) }, false); break
        case 'Circle': done(geoId, { ...geo, center: m(geo.center) }, false); break
        case 'ArcOfCircle': {
          const sp = pointOf(d, geoId, START), ep = pointOf(d, geoId, END)
          const ssp = m(sp), sep = m(ep), scp = m(geo.center)
          const theta1 = fmod(Math.atan2(sep[1] - scp[1], sep[0] - scp[0]), TWO_PI)
          const theta2 = fmod(Math.atan2(ssp[1] - scp[1], ssp[0] - scp[0]), TWO_PI)
          const [a, b] = setTrimPeriodic(theta1, theta2)
          done(geoId, { ...geo, center: scp, start_angle: a, end_angle: b }, true)
          break
        }
        case 'Ellipse': case 'ArcOfEllipse': case 'ArcOfHyperbola': {
          const cp = geo.center, majdir = unit(geo.x_axis), A = geo.major_radius, B = geo.minor_radius
          const df = geo.type === 'ArcOfHyperbola' ? Math.sqrt(A * A + B * B) : Math.sqrt(A * A - B * B)
          const f1 = add(cp, mul(majdir, df)), sf1 = m(f1), scp = m(cp)
          const x_axis = axisDir(sub(sf1, scp), majdir)
          if (geo.type === 'Ellipse') { done(geoId, { ...geo, center: scp, x_axis }, false); break }
          let t1: number, t2: number
          if (geo.type === 'ArcOfEllipse') {
            t1 = TWO_PI - geo.start_angle; t2 = TWO_PI - geo.end_angle;[t1, t2] = [t2, t1]
            if (t1 < 0) { t1 += TWO_PI; t2 += TWO_PI }
            ;[t1, t2] = setTrimPeriodic(t1, t2)
          } else { t1 = -geo.end_angle; t2 = -geo.start_angle }
          done(geoId, stripEnds({ ...geo, center: scp, x_axis, start_angle: t1, end_angle: t2 }), true)
          break
        }
        case 'ArcOfParabola': {
          const majdir = unit(geo.x_axis), f1 = add(geo.center, mul(majdir, geo.focal)), sf1 = m(f1), scp = m(geo.center)
          done(geoId, stripEnds({ ...geo, center: scp, x_axis: axisDir(sub(sf1, scp), majdir), start_angle: -geo.end_angle, end_angle: -geo.start_angle }), true)
          break
        }
        case 'BSplineCurve': done(geoId, { ...geo, poles: geo.poles.map(m), ...(geo.weights ? { weights: [...geo.weights] } : {}), knots: [...geo.knots], mults: [...geo.mults] }, false); break
        case 'Point': done(geoId, { ...geo, at: m(geo.at) }, false); break
      }
    }
    return { geometry: out, geoIdMap, inverted }
  }
  // the reference is a point
  const georef = geometryAt(d, refGeoId)
  let refpoint: XY
  if (georef?.type === 'Point') refpoint = georef.at
  else if (refGeoId === -1 && refPosId === START) refpoint = [0, 0]
  else refpoint = pointOf(d, refGeoId, refPosId)
  const m = (p: XY): XY => add(p, mul(sub(refpoint, p), 2))
  for (const geoId of geoIdList) {
    const geo = geometryAt(d, geoId)
    if (!geo || !shouldCopy(geoId)) continue
    switch (geo.type) {
      case 'LineSegment': done(geoId, { ...geo, start: m(geo.start), end: m(geo.end) }, false); break
      case 'Circle': done(geoId, { ...geo, center: m(geo.center) }, false); break
      case 'ArcOfCircle': {
        const ssp = m(pointOf(d, geoId, START)), sep = m(pointOf(d, geoId, END)), scp = m(geo.center)
        const theta1 = fmod(Math.atan2(ssp[1] - scp[1], ssp[0] - scp[0]), TWO_PI)
        const theta2 = fmod(Math.atan2(sep[1] - scp[1], sep[0] - scp[0]), TWO_PI)
        const [a, b] = setTrimPeriodic(theta1, theta2)
        done(geoId, { ...geo, center: scp, start_angle: a, end_angle: b }, false)
        break
      }
      case 'Ellipse': case 'ArcOfEllipse': case 'ArcOfHyperbola': {
        const cp = geo.center, majdir = unit(geo.x_axis), A = geo.major_radius, B = geo.minor_radius
        const df = geo.type === 'ArcOfHyperbola' ? Math.sqrt(A * A + B * B) : Math.sqrt(A * A - B * B)
        const f1 = add(cp, mul(majdir, df)), sf1 = m(f1), scp = m(cp)
        done(geoId, stripEnds({ ...geo, center: scp, x_axis: axisDir(sub(sf1, scp), majdir) }), false)
        break
      }
      case 'ArcOfParabola': {
        const majdir = unit(geo.x_axis), f1 = add(geo.center, mul(majdir, geo.focal)), sf1 = m(f1), scp = m(geo.center)
        done(geoId, stripEnds({ ...geo, center: scp, x_axis: axisDir(sub(sf1, scp), majdir) }), false)
        break
      }
      // (no isStartEndInverted entry: the map's operator[] reads false)
      case 'BSplineCurve': done(geoId, { ...geo, poles: geo.poles.map(m), ...(geo.weights ? { weights: [...geo.weights] } : {}), knots: [...geo.knots], mults: [...geo.mults] }, null); break
      case 'Point': done(geoId, { ...geo, at: m(geo.at) }, false); break
    }
  }
  return { geometry: out, geoIdMap, inverted }
}

/** SketchObject::addSymmetric(geoIdList, refGeoId, refPosId, addSymmetryConstraints): the mirror images added, with
 *  the constraints among the mirrored elements copied (Python's sketch.addSymmetric leaves addSymmetryConstraints
 *  false); with addSymmetryConstraints (the Symmetry tool's option) only the topological ones, and each mirrored point
 *  tied to its original by a Symmetric constraint (a Coincident on the axis). Returns the last GeoId. */
export function addSymmetric(d: Doc, geoIdList: number[], refGeoId: number, refPosId: PointPos = NONE, addSymmetryConstraints = false): number {
  const constrvals = d.constraints, newconstrVals = [...constrvals]
  const refIsLine = refPosId === NONE
  const refIsAxisAligned = refGeoId === V_AXIS || refGeoId === H_AXIS || !refIsLine
    || constrvals.some((c) => c.first === refGeoId && (c.type === 'Vertical' || c.type === 'Horizontal'))
  const { geometry: symgeos0, geoIdMap, inverted } = getSymmetric(d, geoIdList, refGeoId, refPosId)
  const isInverted = (g: number) => inverted.get(g) ?? false
  // perturb the arcs, else the solver cannot tell a Symmetric from an Equal (FreeCAD #13551)
  const symgeos = addSymmetryConstraints
    ? symgeos0.map((g) => { if (g.type !== 'ArcOfCircle') return g; const [a, b] = setTrimPeriodic(g.start_angle + ANGULAR, g.end_angle); return { ...g, start_angle: a, end_angle: b } })
    : symgeos0
  const original: Doc = { geometry: d.geometry, constraints: constrvals }
  d.geometry = [...d.geometry, ...symgeos]
  const flip = (g: number, pos: PointPos): PointPos => (isInverted(g) ? (pos === START ? END : pos === END ? START : pos) : pos)
  for (const constr of constrvals) {
    const first = geoIdMap.get(constr.first)
    if (first === undefined) continue
    if (addSymmetryConstraints && constr.type !== 'InternalAlignment') {
      // only the topological constraints keep the shape: Coincident, endpoint-to-endpoint Tangent / Perpendicular
      const keep = constr.type === 'Coincident' || ((constr.type === 'Tangent' || constr.type === 'Perpendicular') && constr.firstPos !== NONE && constr.secondPos !== NONE)
      if (!keep) continue
    }
    if (constr.second === GEO_UNDEF) {
      if (refIsAxisAligned && (constr.type === 'DistanceX' || constr.type === 'DistanceY')) continue
      if (!refIsAxisAligned && (constr.type === 'DistanceX' || constr.type === 'DistanceY' || constr.type === 'Vertical' || constr.type === 'Horizontal')) continue
      newconstrVals.push({ ...constr, name: '', first })
      continue
    }
    const second = geoIdMap.get(constr.second)
    if (second === undefined) continue
    if (constr.third === GEO_UNDEF) {
      if (!['Coincident', 'Perpendicular', 'Parallel', 'Tangent', 'Distance', 'Equal', 'Angle', 'PointOnObject', 'InternalAlignment'].includes(constr.type)) continue
      const n: Constraint = { ...constr, name: '', first, firstPos: flip(constr.first, constr.firstPos), second, secondPos: flip(constr.second, constr.secondPos) }
      // a dependent symmetric copy: Tangent / Perpendicular would over-constrain the angle the symmetries fix
      if (addSymmetryConstraints && (n.type === 'Tangent' || n.type === 'Perpendicular')) n.type = 'Coincident'
      // AutoLockTangencyAndPerpty(bForce): the solver locks the tangency of the new geometry (a value of 0 here)
      if (n.type === 'Tangent' || n.type === 'Perpendicular') n.value = 0
      if (constr.type === 'Angle' && refPosId === NONE) n.value = -constr.value
      // setOrientation: the solver reads a signed constraint's side from the geometry (no orientation kept here)
      newconstrVals.push(n)
      continue
    }
    const third = geoIdMap.get(constr.third)
    if (third === undefined) continue
    newconstrVals.push({ ...constr, name: '', first, firstPos: flip(constr.first, constr.firstPos), second, secondPos: flip(constr.second, constr.secondPos),
      third, thirdPos: flip(constr.third, constr.thirdPos) })
  }
  if (addSymmetryConstraints) {
    const constrained = new Set<string>()
    const key = (g: number, p: PointPos) => `${g}:${p}`
    const markPointConstrained = (g: number, p: PointPos) => {
      constrained.add(key(g, p))
      for (const [mg, mp] of coincidentPoints(constrvals, g, p)) constrained.add(key(mg, mp))
    }
    const isPointOnReference = (pt: XY) => {
      if (refPosId === NONE) {
        const ref = geometryAt(original, refGeoId)
        if (ref?.type === 'LineSegment') {
          const [l1, l2] = [ref.start, ref.end], dx = l2[0] - l1[0], dy = l2[1] - l1[1], lenSq = dx * dx + dy * dy
          if (lenSq > CONFUSION * CONFUSION) {
            const area = (pt[0] - l1[0]) * dy - (pt[1] - l1[1]) * dx
            if (Math.abs(area) / Math.sqrt(lenSq) < CONFUSION) return true
          }
        }
      } else {
        const refPt = refGeoId === RT_PNT ? [0, 0] as XY : pointOf(original, refGeoId, refPosId)
        if (len(sub(pt, refPt)) < CONFUSION) return true
      }
      return false
    }
    const createSymConstr = (a: number, b: number, ap: PointPos, bp: PointPos) => {
      if (constrained.has(key(a, ap))) return
      if (isPointOnReference(pointOf(original, a, ap))) newconstrVals.push(constraint('Coincident', a, ap, b, bp))
      else newconstrVals.push(constraint('Symmetric', a, ap, b, bp, refGeoId, refPosId))
      markPointConstrained(a, ap)
    }
    const createEquality = (a: number, b: number) => newconstrVals.push(constraint('Equal', a, NONE, b, NONE))
    for (const [g1, g2] of [...geoIdMap].sort((x, y) => x[0] - y[0])) {
      const geo = geometryAt(original, g1)!
      const s = isInverted(g1) ? END : START, e = isInverted(g1) ? START : END
      if (geo.type === 'LineSegment') { if (!isInternalAligned(original, g1)) { createSymConstr(g1, g2, START, s); createSymConstr(g1, g2, END, e) } }
      else if (geo.type === 'Circle' || geo.type === 'Ellipse') { createEquality(g1, g2); createSymConstr(g1, g2, MID, MID) }
      else if (geo.type === 'ArcOfCircle' || geo.type === 'ArcOfEllipse' || geo.type === 'ArcOfHyperbola' || geo.type === 'ArcOfParabola') {
        createEquality(g1, g2); createSymConstr(g1, g2, START, s); createSymConstr(g1, g2, END, e)
      } else if (geo.type === 'Point') { if (!isInternalAligned(original, g1)) createSymConstr(g1, g2, START, START) }
      // a B-spline is symmetric through its internal pole circles
    }
  }
  d.constraints = newconstrVals
  return d.geometry.length - 1
}

// ── copy, clone, move, array (SketchObject::addCopy) ─────────────────────────────────────────────────────────────
/** Base::ValueError from addCopy, with FreeCAD's message. */
export class XformError extends Error {}
const SINGLE_TO_EQUAL = ['DistanceX', 'DistanceY', 'Distance', 'Diameter', 'Weight', 'Radius']
/** SketchObject::addCopy(geoIdList, displacement, moveonly, clone, csize, rsize, constraindisplacement, perpscale):
 *  moves the geometry (moveonly), or copies it csize times along the displacement and rsize times across it (the
 *  perpendicular displacement scaled by perpscale), each copy with the constraints among the copied elements (a clone
 *  turns a dimension on one element into an Equal to the original, an angle into a Parallel) and a construction line
 *  from the previous copy's reference point (the first element's start, or centre) dimensioned or tied to the first
 *  one. FreeCAD 26.3 adds that line for a plain copy too, and constraindisplacement changes nothing. Returns the last
 *  GeoId; throws an XformError when the first element is internal geometry without the geometry it defines. */
export function addCopy(d: Doc, geoIdList: number[], displacement: XY, moveonly = false, clone = false, csize = 2, rsize = 1,
  constraindisplacement = false, perpscale = 1.0): number {
  const geovals = d.geometry
  const newgeoVals = [...geovals]
  const constrvals = d.constraints, newconstrVals = [...constrvals]
  const list = geoIdList.length ? [...geoIdList] : geovals.map((_, i) => i)
  let cgeoid = geovals.length
  let iterfirstgeoid = -1, iterfirstpoint: XY = [0, 0], refgeoid = -1, colrefgeoid = 0, rowrefgeoid = 0
  let currentrowfirstgeoid = -1, prevrowstartfirstgeoid = -1, prevfirstgeoid = -1
  let refposId: PointPos = NONE
  const geoIdMap = new Map<number, number>()
  const perp: XY = [perpscale * displacement[1], perpscale * -displacement[0]]
  const definedOf = (g: number) => { const c = constrvals.find((k) => k.type === 'InternalAlignment' && k.first === g); return c ? c.second : GEO_UNDEF }
  const internal = (g: number) => constrvals.some((k) => k.type === 'InternalAlignment' && k.first === g)
  const original: Doc = { geometry: geovals, constraints: constrvals }
  const makeCopyAtRowColumn = (x: number, y: number) => {
    if (x === 0 && y === 0) {
      const g0 = list[0], geo = geometryAt(original, g0)!
      if (internal(g0) && !moveonly && !list.includes(definedOf(g0)))
        throw new XformError('A move/copy/array operation on an internal alignment geometry is only possible together with the geometry it defines.')
      refgeoid = g0; currentrowfirstgeoid = refgeoid; iterfirstgeoid = refgeoid
      refposId = geo.type === 'Circle' || geo.type === 'Ellipse' ? MID : START
      return
    }
    prevfirstgeoid = iterfirstgeoid
    iterfirstgeoid = cgeoid
    if (x === 0) { prevrowstartfirstgeoid = currentrowfirstgeoid; currentrowfirstgeoid = cgeoid }
    // FreeCAD's sum: point + x * displacement + y * perpendicular, in that order
    const shift = (p: XY): XY => add(add(p, mul(displacement, x)), mul(perp, y))
    list.forEach((g, k) => {
      // a move changes the geometry in place (a GeoId listed twice moves twice)
      const geo = moveonly && g >= 0 ? newgeoVals[g] : geometryAt(original, g)
      if (!geo) return
      if (internal(g) && !moveonly && !list.includes(definedOf(g))) return
      let copy: Geo
      let firstPoint: XY
      switch (geo.type) {
        case 'LineSegment': copy = { ...geo, start: shift(geo.start), end: shift(geo.end) }; firstPoint = copy.start; break
        case 'Circle': copy = { ...geo, center: shift(geo.center) }; firstPoint = copy.center; break
        case 'ArcOfCircle': copy = { ...geo, center: shift(geo.center) }; firstPoint = getPoint([copy], 0, START)!; break
        case 'Ellipse': copy = { ...geo, center: shift(geo.center) }; firstPoint = copy.center; break
        case 'ArcOfEllipse': case 'ArcOfHyperbola': case 'ArcOfParabola':
          copy = stripEnds({ ...geo, center: shift(geo.center) }); firstPoint = getPoint([copy], 0, START)!; break
        case 'BSplineCurve': copy = { ...geo, poles: geo.poles.map(shift), ...(geo.weights ? { weights: [...geo.weights] } : {}), knots: [...geo.knots], mults: [...geo.mults] }; firstPoint = getPoint([copy], 0, START)!; break
        case 'Point': copy = { ...geo, at: shift(geo.at) }; firstPoint = copy.at; break
        default: return
      }
      if (k === 0) iterfirstpoint = firstPoint
      if (moveonly) newgeoVals[g] = copy
      else { newgeoVals.push(copy); if (!geoIdMap.has(g)) geoIdMap.set(g, cgeoid); cgeoid++ }
    })
    if (moveonly) return
    for (const constr of constrvals) {
      const fit = geoIdMap.get(constr.first)
      if (fit === undefined) continue
      if (constr.second === GEO_UNDEF) {
        if ((constr.type === 'DistanceX' || constr.type === 'DistanceY') && constr.firstPos !== NONE) continue
        if (SINGLE_TO_EQUAL.includes(constr.type) && clone) {
          // a dimension on one element becomes an equality to the original in a clone
          newconstrVals.push({ ...constr, type: 'Equal', driving: true, second: fit })
          continue
        }
        if (!(constr.type === 'Angle' && clone)) { newconstrVals.push({ ...constr, first: fit }); continue }
        // an angle on a line becomes a parallel to the original in a clone
        if (geometryAt(original, constr.first)?.type === 'LineSegment') newconstrVals.push({ ...constr, type: 'Parallel', driving: true, second: fit })
        continue
      }
      const sit = geoIdMap.get(constr.second)
      if (sit === undefined) continue
      if (constr.third === GEO_UNDEF) {
        if ((constr.type === 'DistanceX' || constr.type === 'DistanceY' || constr.type === 'Distance') && constr.first === constr.second && clone) {
          // a distance between two points of one line becomes the line's equality in a clone
          newconstrVals.push({ ...constr, type: 'Equal', driving: true, firstPos: NONE, second: fit, secondPos: NONE })
          continue
        }
        newconstrVals.push({ ...constr, first: fit, second: sit })
        continue
      }
      // FreeCAD 26.3 copies a three-element constraint only when its third element is NOT copied, and reads the
      // third GeoId from the map's end (libstdc++: the high half of the map's size, 0)
      if (geoIdMap.has(constr.third)) continue
      newconstrVals.push({ ...constr, first: fit, second: sit, third: 0 })
    }
    if (!constraindisplacement) geoIdMap.clear()
    // the construction line from the previous copy's reference point to this one's
    const sp = add(pointOf(original, refgeoid, refposId), x === 0 ? add(mul(displacement, x), mul(perp, y - 1)) : add(mul(displacement, x - 1), mul(perp, y)))
    // GeomLineSegment::setPoints refuses a line of no length (gp::Resolution)
    if (sp[0] === iterfirstpoint[0] && sp[1] === iterfirstpoint[1]) throw new XformError('Both points are equal')
    newgeoVals.push({ type: 'LineSegment', start: sp, end: iterfirstpoint, construction: true })
    if (x === 0) {
      newconstrVals.push(constraint('Coincident', prevrowstartfirstgeoid, refposId, cgeoid, START))
      newconstrVals.push(constraint('Coincident', iterfirstgeoid, refposId, cgeoid, END))
      if (y === 1) {
        rowrefgeoid = cgeoid
        cgeoid++
        if (perpscale === 1.0) newconstrVals.push(constraint('Equal', rowrefgeoid, NONE, colrefgeoid, NONE))
        else newconstrVals.push(constraint('Distance', rowrefgeoid, NONE, GEO_UNDEF, NONE, GEO_UNDEF, NONE, len(perp)))
        newconstrVals.push(constraint('Perpendicular', rowrefgeoid, NONE, colrefgeoid, NONE))
      } else {
        cgeoid++
        newconstrVals.push(constraint('Equal', rowrefgeoid, NONE, cgeoid - 1, NONE))
        newconstrVals.push(constraint('Perpendicular', cgeoid - 1, NONE, colrefgeoid, NONE))
      }
    } else {
      newconstrVals.push(constraint('Coincident', prevfirstgeoid, refposId, cgeoid, START))
      newconstrVals.push(constraint('Coincident', iterfirstgeoid, refposId, cgeoid, END))
      if (y === 0 && x === 1) {
        colrefgeoid = cgeoid
        cgeoid++
        newconstrVals.push(constraint('Distance', colrefgeoid, NONE, GEO_UNDEF, NONE, GEO_UNDEF, NONE, len(displacement)))
        newconstrVals.push(constraint('Angle', colrefgeoid, NONE, GEO_UNDEF, NONE, GEO_UNDEF, NONE, Math.atan2(displacement[1], displacement[0])))
      } else {
        cgeoid++
        newconstrVals.push(constraint('Equal', colrefgeoid, NONE, cgeoid - 1, NONE))
        newconstrVals.push(constraint('Parallel', cgeoid - 1, NONE, colrefgeoid, NONE))
      }
    }
    geoIdMap.clear()
  }
  for (let y = 0; y < rsize; y++) for (let x = 0; x < csize; x++) makeCopyAtRowColumn(x, y)
  d.geometry = newgeoVals
  d.constraints = newconstrVals
  return d.geometry.length - 1
}
/** sketch.addMove(geoIds, vector): addCopy moving the geometry in place (no constraint changes, no solve). */
export const addMove = (d: Doc, geoIdList: number[], displacement: XY) => addCopy(d, geoIdList, displacement, true)
/** sketch.addRectangularArray(geoIds, vector, clone, rows, cols, constrainDisplacement, perpScale): addCopy with csize
 *  the Python's rows and rsize its cols (the Rectangular Array tool passes its columns as rows). */
export const addRectangularArray = (d: Doc, geoIdList: number[], displacement: XY, clone: boolean, rows: number, cols: number,
  constrainDisplacement = false, perpscale = 1.0) => addCopy(d, geoIdList, displacement, false, clone, rows, cols, constrainDisplacement, perpscale)

// ── SketchObject::removeAxesAlignment ────────────────────────────────────────────────────────────────────────────
/** SketchObject::removeAxesAlignment(geoIdList): on the constraints touching the elements, the first Horizontal (and
 *  the first Vertical) of a line goes and the next ones become Parallel to its line, a Symmetric about an axis and a
 *  point on an axis go, and a DistanceX / DistanceY becomes a Distance. True when something changed. */
export function removeAxesAlignment(d: Doc, geoIdList: number[]): boolean {
  if (!geoIdList.length) return false
  const out: Constraint[] = []
  let changed = false
  const reference: Record<'Horizontal' | 'Vertical', number> = { Horizontal: GEO_UNDEF, Vertical: GEO_UNDEF }
  for (const c of d.constraints) {
    if (!geoIdList.some((g) => c.first === g || c.second === g || c.third === g)) { out.push(c); continue }
    switch (c.type) {
      case 'Horizontal': case 'Vertical':
        if (c.firstPos === NONE && c.secondPos === NONE) {
          changed = true
          if (reference[c.type] === GEO_UNDEF) reference[c.type] = c.first
          else out.push(constraint('Parallel', reference[c.type], NONE, c.first, NONE))
        } else out.push(c)
        break
      case 'Symmetric':
        if ((c.third === H_AXIS || c.third === V_AXIS) && c.thirdPos === NONE) changed = true
        else out.push(c)
        break
      case 'PointOnObject':
        if ((c.second === H_AXIS || c.second === V_AXIS) && c.secondPos === NONE) changed = true
        else out.push(c)
        break
      case 'DistanceX': case 'DistanceY': changed = true; out.push({ ...c, type: 'Distance' }); break
      default: out.push(c)
    }
  }
  if (changed) d.constraints = out
  return changed
}

// ── the controllable transform tools' shapes (DrawSketchHandlerTranslate.h, DrawSketchHandlerRotate.h,
//    DrawSketchHandlerScale.h: createShape) ─────────────────────────────────────────────────────────────────────
/** The geometry with each point mapped (a translation or a rotation: lengths kept); `dir` maps a direction. */
function mapGeometry(g: Geo, pt: (p: XY) => XY, dir: (v: XY) => XY, turn: number): Geo {
  switch (g.type) {
    case 'Point': return { ...g, at: pt(g.at) }
    case 'LineSegment': return { ...g, start: pt(g.start), end: pt(g.end) }
    case 'Circle': return { ...g, center: pt(g.center) }
    case 'ArcOfCircle': { const [a, b] = setTrimPeriodic(g.start_angle + turn, g.end_angle + turn); return { ...g, center: pt(g.center), start_angle: a, end_angle: b } }
    case 'Ellipse': return { ...g, center: pt(g.center), x_axis: unit(dir(g.x_axis)) }
    case 'ArcOfEllipse': case 'ArcOfHyperbola': case 'ArcOfParabola': return stripEnds({ ...g, center: pt(g.center), x_axis: unit(dir(g.x_axis)) })
    case 'BSplineCurve': return { ...g, poles: g.poles.map(pt), ...(g.weights ? { weights: [...g.weights] } : {}), knots: [...g.knots], mults: [...g.mults] }
  }
}
/** createShape's moves of a copy by vec (setCenter / setPoints / setPoles + vec). */
export const translateGeometry = (g: Geo, v: XY) => mapGeometry(g, (p) => add(p, v), (x) => x, 0)
/** Base::Matrix4D(center, Z, angle) applied by Geometry::transform. */
export function rotateGeometry(g: Geo, c: XY, angle: number): Geo {
  const cs = Math.cos(angle), sn = Math.sin(angle)
  const rot = (v: XY): XY => [cs * v[0] - sn * v[1], sn * v[0] + cs * v[1]]
  return mapGeometry(g, (p) => add(c, rot(sub(p, c))), rot, angle)
}
/** DrawSketchHandlerScale::createShape for one geometry: radii, focal and a parabola's range times k, points about ref. */
export function scaleGeometry(g: Geo, ref: XY, k: number): Geo {
  const sp = (p: XY): XY => add(mul(sub(p, ref), k), ref)
  switch (g.type) {
    case 'Circle': return { ...g, radius: g.radius * k, center: sp(g.center) }
    case 'ArcOfCircle': return { ...g, radius: g.radius * k, center: sp(g.center) }
    case 'LineSegment': return { ...g, start: sp(g.start), end: sp(g.end) }
    case 'Ellipse': return { ...g, major_radius: g.major_radius * k, minor_radius: g.minor_radius * k, center: sp(g.center) }
    case 'ArcOfEllipse': case 'ArcOfHyperbola': return stripEnds({ ...g, major_radius: g.major_radius * k, minor_radius: g.minor_radius * k, center: sp(g.center) })
    case 'ArcOfParabola': return stripEnds({ ...g, focal: g.focal * k, start_angle: g.start_angle * k, end_angle: g.end_angle * k, center: sp(g.center) })
    case 'BSplineCurve': return { ...g, poles: g.poles.map(sp), ...(g.weights ? { weights: [...g.weights] } : {}), knots: [...g.knots], mults: [...g.mults] }
    case 'Point': return { ...g, at: sp(g.at) }
  }
}
/** SketcherGui::indexOfGeoId: the place in the list, GeoUndef for GeoUndef, else -1. */
const indexOfGeoId = (list: number[], g: number) => (g === GEO_UNDEF ? GEO_UNDEF : list.indexOf(g))
export type Shape = { geometry: Geo[]; constraints: Constraint[]; deleteOriginal: boolean }
/** DrawSketchHandlerTranslate::createShape(false): the copies at firstFactor × v1 + secondFactor × v2 (a single element
 *  and row moves the original: deleteOriginal), and the constraints among the copied elements. */
export function translateShape(d: Doc, list: number[], v1: XY, v2: XY, numberOfCopies: number, secondNumberOfCopies: number,
  firstSymmetric: boolean, secondSymmetric: boolean, cloneConstraints: boolean): Shape {
  const offsets: [number, number][] = []
  let deleteOriginal = false
  if (numberOfCopies === 1 && secondNumberOfCopies === 1) { deleteOriginal = true; offsets.push([1, 0]) }
  else {
    const build = (n: number, sym: boolean) => {
      n = Math.max(n, 1)
      if (!sym) return Array.from({ length: n }, (_, i) => i)
      const side = Math.trunc(n / 2), hasOriginal = n % 2 === 1, f: number[] = []
      if (hasOriginal) f.push(0)
      for (let i = 1; i <= side; i++) f.push(hasOriginal ? i : i - 0.5)
      for (let i = 1; i <= side; i++) f.push(hasOriginal ? -i : 0.5 - i)
      return f
    }
    const hasOriginal = (f: number[]) => f.some((x) => Math.abs(x) < CONFUSION)
    const f1 = build(numberOfCopies, firstSymmetric), f2 = build(secondNumberOfCopies, secondSymmetric)
    deleteOriginal = !(hasOriginal(f1) && hasOriginal(f2))
    for (const b of f2) for (const a of f1) { if (Math.abs(a) < CONFUSION && Math.abs(b) < CONFUSION) continue; offsets.push([a, b]) }
  }
  const geometry: Geo[] = []
  for (const [a, b] of offsets) {
    const v = add(mul(v1, a), mul(v2, b))
    for (const g of list) geometry.push(translateGeometry(geometryAt(d, g)!, v))
  }
  const first = d.geometry.length, size = list.length, out: Constraint[] = [], hasEqual: number[] = []
  for (const c of d.constraints) {
    const fi = indexOfGeoId(list, c.first), si = indexOfGeoId(list, c.second), ti = indexOfGeoId(list, c.third)
    for (let k = 0; k < offsets.length; k++) {
      const fk = first + fi + size * k, sk = first + si + size * k, tk = first + ti + size * k
      const n: Constraint = { ...c, first: fk }
      if (['Symmetric', 'Tangent', 'Perpendicular', 'Angle'].includes(c.type) && fi >= 0 && si >= 0 && ti >= 0) { n.second = sk; n.third = tk }
      else if (['Coincident', 'Tangent', 'Symmetric', 'Perpendicular', 'Parallel', 'Equal', 'Angle', 'PointOnObject', 'Horizontal', 'Vertical', 'InternalAlignment'].includes(c.type)
        && fi >= 0 && si >= 0 && ti === GEO_UNDEF) n.second = sk
      else if (['Radius', 'Diameter', 'Weight'].includes(c.type) && fi >= 0) {
        if (!(deleteOriginal || !cloneConstraints)) { n.type = 'Equal'; n.first = c.first; n.second = fk }
      } else if (['Distance', 'DistanceX', 'DistanceY'].includes(c.type) && fi >= 0 && si >= 0) {
        if (!deleteOriginal && cloneConstraints && c.first === c.second) {
          if (hasEqual.includes(sk)) continue
          n.type = 'Equal'; n.first = c.first; n.second = sk; hasEqual.push(sk)
        } else n.second = sk
      } else if (['Block', 'Horizontal', 'Vertical'].includes(c.type) && fi >= 0) n.first = fk
      else continue
      out.push(n)
    }
  }
  return { geometry, constraints: out, deleteOriginal }
}
const FULL_TURN = 2 * Math.PI
/** DrawSketchHandlerRotate's angle helpers. */
export const clampToFullTurn = (a: number) => (a > FULL_TURN ? FULL_TURN : a < -FULL_TURN ? -FULL_TURN : a)
const isOneFullTurn = (a: number) => Math.abs(Math.abs(a) - FULL_TURN) < ANGULAR
const angleForShapeCreation = (a: number) => (Math.abs(a) < ANGULAR ? FULL_TURN : clampToFullTurn(a))
export function closestContinuousAngle(angle: number, previous: number) {
  if (Math.abs(angle) < ANGULAR) return 0
  let closest = angle
  for (const cand of [angle + FULL_TURN, angle - FULL_TURN]) if (Math.abs(cand) <= FULL_TURN && Math.abs(cand - previous) < Math.abs(closest - previous)) closest = cand
  return closest
}
/** DrawSketchHandlerRotate::createShape(false): numberOfCopies elements spread over totalAngle about the centre (one
 *  element rotates the original: deleteOriginal), symmetric ones on both sides, and the constraints among the copies. */
export function rotateShape(d: Doc, list: number[], center: XY, totalAngle: number, numberOfCopies: number, symmetric: boolean, cloneConstraints: boolean): Shape & { individualAngle: number } {
  const elements = Math.max(numberOfCopies, 1), transformOriginal = elements === 1
  const toMake = transformOriginal ? 1 : symmetric ? Math.trunc(elements / 2) : elements - 1
  const deleteOriginal = transformOriginal || (symmetric && elements % 2 === 0)
  const shapeAngle = angleForShapeCreation(totalAngle)
  let divisor = deleteOriginal && symmetric && !transformOriginal ? toMake - 0.5 : toMake
  if (toMake > 0 && isOneFullTurn(shapeAngle)) divisor = transformOriginal ? 1 : elements
  const individualAngle = shapeAngle / divisor
  const factors: number[] = []
  for (let i = 1; i <= toMake; i++) factors.push(transformOriginal ? i : deleteOriginal ? i - 0.5 : i)
  if (symmetric && !transformOriginal) for (let i = 1; i <= toMake; i++) factors.push(deleteOriginal ? 0.5 - i : -i)
  const geometry: Geo[] = []
  for (const f of factors) for (const g of list) geometry.push(rotateGeometry(geometryAt(d, g)!, center, individualAngle * f))
  const first = d.geometry.length, size = list.length, out: Constraint[] = [], hasEqual: number[] = []
  for (const c of d.constraints) {
    const fi = indexOfGeoId(list, c.first), si = indexOfGeoId(list, c.second), ti = indexOfGeoId(list, c.third)
    for (let k = 0; k < factors.length; k++) {
      const fk = first + fi + size * k, sk = first + si + size * k, tk = first + ti + size * k
      const n: Constraint = { ...c, first: fk }
      if (['Symmetric', 'Tangent', 'Perpendicular', 'Angle'].includes(c.type) && fi >= 0 && si >= 0 && ti >= 0) { n.second = sk; n.third = tk }
      else if (['Coincident', 'Tangent', 'Symmetric', 'Perpendicular', 'Parallel', 'Equal', 'Angle', 'PointOnObject', 'InternalAlignment'].includes(c.type)
        && fi >= 0 && si >= 0 && ti === GEO_UNDEF) n.second = sk
      else if (['Radius', 'Diameter', 'Weight'].includes(c.type) && fi >= 0) {
        if (!(deleteOriginal || !cloneConstraints)) { n.type = 'Equal'; n.first = c.first; n.second = fk }
      } else if (['Distance', 'DistanceX', 'DistanceY'].includes(c.type) && fi >= 0) {
        if (!deleteOriginal && cloneConstraints && (c.first === c.second || si < 0)) {
          if (hasEqual.includes(fk)) continue
          n.type = 'Equal'; n.first = c.first; n.second = fk; hasEqual.push(fk)
        } else if (c.type === 'Distance') { if (si >= 0) n.second = sk }
        else continue // DistanceX / DistanceY are left out (FreeCAD: they would flip the copy)
      } else if (c.type === 'Block' && fi >= 0) n.first = fk
      else continue
      out.push(n)
    }
  }
  return { geometry, constraints: out, deleteOriginal, individualAngle }
}
export type LabelToScale = { constrId: number; position: number; distance: number }
/** DrawSketchHandlerScale::createShape(false): the scaled geometry, and the constraints among it (the dimensions times
 *  k); none to the axes or the external geometry. The labels to scale are listed as FreeCAD lists them (an entry for
 *  every constraint on a scaled element, numbered by the constraints kept). */
export function scaleShape(d: Doc, list: number[], ref: XY, k: number, deleteOriginal: boolean, allowOriginConstraint = false): Shape & { labels: LabelToScale[] } {
  const geometry = list.map((g) => scaleGeometry(geometryAt(d, g)!, ref, k))
  const first = deleteOriginal ? d.geometry.length - list.length : d.geometry.length
  const isExt = (g: number) => g !== GEO_UNDEF && g <= -3
  const axis = (g: number) => g === V_AXIS || g === H_AXIS
  const skip = (c: Constraint) => c.first === GEO_UNDEF || (!allowOriginConstraint && (axis(c.first) || axis(c.second) || axis(c.third))) || isExt(c.first) || isExt(c.second) || isExt(c.third)
  const offset = (g: number) => {
    if (g < 0) return allowOriginConstraint && axis(g) ? g : GEO_UNDEF
    const i = list.indexOf(g)
    return i < 0 ? GEO_UNDEF : i + first
  }
  const out: Constraint[] = [], labels: LabelToScale[] = []
  let idx = 0
  for (const c of d.constraints) {
    if (skip(c)) continue
    const f = offset(c.first), s = offset(c.second), t = offset(c.third)
    const n: Constraint = { ...c }
    if (f !== GEO_UNDEF) labels.push({ constrId: idx, position: c.labelPosition, distance: c.labelDistance })
    const U = GEO_UNDEF
    if (['Symmetric', 'Tangent', 'Perpendicular', 'Angle'].includes(c.type) && f !== U && s !== U && t !== U) { n.first = f; n.second = s; n.third = t }
    else if (['Coincident', 'Tangent', 'Symmetric', 'Perpendicular', 'Parallel', 'Equal', 'Angle', 'PointOnObject', 'InternalAlignment'].includes(c.type) && f !== U && s !== U && t === U) { n.first = f; n.second = s }
    else if (c.type === 'Angle' && f !== U && s === U && t === U) n.first = f
    else if ((c.type === 'Radius' || c.type === 'Diameter') && f !== U) { n.first = f; n.value = c.value * k }
    else if (['Distance', 'DistanceX', 'DistanceY'].includes(c.type) && f !== U && s !== U) { n.first = f; n.second = s; n.value = c.value * k }
    else if (['Distance', 'DistanceX', 'DistanceY'].includes(c.type) && f !== U && c.second === U) { n.first = f; n.value = c.value * k }
    else if ((c.type === 'Block' || c.type === 'Weight') && f !== U) n.first = f
    else if ((c.type === 'Vertical' || c.type === 'Horizontal') && f !== U && (c.second === U || s !== U)) { n.first = f; n.second = s }
    else continue
    out.push(n)
    idx++
  }
  return { geometry, constraints: out, deleteOriginal, labels }
}
